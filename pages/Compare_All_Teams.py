import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta
from dateutil import tz as dateutil_tz
try:
    from streamlit_plotly_events import plotly_events
    HAS_EVENTS = True
except Exception:
    HAS_EVENTS = False

from hf.espn import get_teams
from hf.flu import compute_honolulu_flu

st.set_page_config(page_title="Honolulu Flu — Compare Teams", page_icon="📊", layout="wide")

teams = get_teams()
team_id_name = {t["id"]: t["displayName"] for t in teams}
team_logo = {t["displayName"]: t.get("logo") for t in teams}

def _get_qp(key: str, default: str) -> str:
    try:
        val = st.query_params.get(key, default)
        return val if isinstance(val, str) else default
    except Exception:
        try:
            return (st.experimental_get_query_params().get(key, [default]) or [default])[0]
        except Exception:
            return default

def _set_qps(qps: dict) -> None:
    try:
        for k, v in qps.items():
            st.query_params[k] = str(v)
    except Exception:
        st.experimental_set_query_params(**{k: str(v) for k, v in qps.items()})

st.sidebar.subheader("Filters")
play = st.sidebar.selectbox(
    "Games to include",
    options=["play", "beat"],
    index=["play", "beat"].index(_get_qp("play", "play")),
    format_func=lambda v: ("All games" if v == "play" else "Beat opponent only"),
    help="All games = every game vs the selected team. Beat opponent = only games the team won.",
    key="play_all_select",
)
compare = st.sidebar.selectbox(
    "Following game is",
    options=["week", "game"],
    index=["week", "game"].index(_get_qp("compare", "week")),
    format_func=lambda v: ("Next NFL week" if v == "week" else "Next played game"),
    help="Next NFL week accounts for byes; Next played game ignores byes.",
    key="compare_all_select",
)
season_options = [2025, 2024, 2023, 2022, 2021]
start = st.sidebar.selectbox("From season", options=season_options, index=season_options.index(int(_get_qp("start", "2024"))), help="Start season (inclusive)", key="start_all_select")
end = st.sidebar.selectbox("Through season", options=season_options, index=season_options.index(int(_get_qp("end", "2025"))), help="End season (inclusive)", key="end_all_select")
if end < start:
    st.sidebar.error("End season must be ≥ start season")
seasons = list(range(start, end + 1)) if end >= start else []
_set_qps({"play": play, "compare": compare, "start": start, "end": end})

st.title("📊 Honolulu Flu — All Teams")
st.caption("Comparison of Honolulu Flu % across teams (same filters as main page).")

EASTERN = dateutil_tz.gettz("US/Eastern")

def _should_refresh(last_fetched: datetime | None) -> bool:
    now = datetime.now(EASTERN)
    if not last_fetched:
        return True
    if now - last_fetched > timedelta(hours=6):
        return True
    if now.weekday() in [0, 3, 5, 6] and now.hour >= 23:
        return True
    if now.weekday() == 6 and ((now.hour == 16 and now.minute >= 35) or (now.hour == 17 and now.minute <= 15)):
        return True
    if now.weekday() == 6 and (now.hour in [20, 21]):
        return True
    if now.weekday() == 6 and (now.hour > 23 or (now.hour == 23 and now.minute >= 30)):
        return True
    return False

@st.cache_data(ttl=0, show_spinner=False)
def _compute_all_rows(_seasons: tuple[int, ...], _play: str, _compare: str) -> pd.DataFrame:
    tlist = get_teams()
    rows_local = []
    for t in tlist:
        sid = t["id"]
        name = t["displayName"]
        try:
            r = compute_honolulu_flu(seasons=_seasons, play_mode=_play, follow_mode=_compare, subject_team_id=sid)
        except Exception:
            r = []
        df = pd.DataFrame([
            {"flu": (1 if (getattr(x, "honolulu_flu_loss", None) is True) else (0 if getattr(x, "honolulu_flu_loss", None) is False else None)), "opp_next_result": getattr(x, "opp_next_result", None)} for x in r
        ])
        considered = df[df["opp_next_result"].isin(["W", "L", "T"])]
        total = len(considered)
        pct = (considered["flu"].sum() / total * 100.0) if total else 0.0
        rows_local.append({"Team": name, "Flu %": pct, "Total": total})
    return pd.DataFrame(rows_local)

# Smart cache control
if _should_refresh(st.session_state.get("last_fetched_all")):
    st.cache_data.clear()
    st.session_state["last_fetched_all"] = datetime.now(EASTERN)

with st.spinner("Computing Honolulu Flu across all teams..."):
    rows_df = _compute_all_rows(tuple(seasons), play, compare) if seasons else pd.DataFrame(columns=["Team", "Flu %", "Total"])

res = rows_df.round({"Flu %": 1}).sort_values(["Flu %"], ascending=[False])
# Slightly larger font for the table
st.markdown("<style>div[data-testid='stDataFrame'] * {font-size: 1.05rem;}</style>", unsafe_allow_html=True)
st.dataframe(res, use_container_width=True, hide_index=True)

color_map = {t["displayName"]: (f"#{t['color']}" if t.get("color") else "#0076B6") for t in teams}
fig = px.bar(res, x="Team", y="Flu %", color="Team", color_discrete_map=color_map)
# Title reflecting filters
title_play = "All games" if play == "play" else "Wins Only"
title_follow = "Following Week" if compare == "week" else "Following Game"
title_text = f"Honolulu Flu % by Team, {start}–{end} • {title_play} • {title_follow}"
fig.update_traces(text=res["Flu %"], texttemplate="%{text:.1f}", textposition="outside")

# Compute y-axis padding so logos and text aren't clipped
y_max = float(res["Flu %"].max() or 0.0)
pad = max(6.0, y_max * 0.22)

# Attempt to annotate bars with logos using layout images
for i, row in res.iterrows():
    logo = team_logo.get(row["Team"]) or ""
    if not logo:
        continue
    fig.add_layout_image(
        dict(
            source=logo,
            x=row["Team"],
            y=row["Flu %"] + min(pad * 0.4, 6.0),
            xref="x",
            yref="y",
            sizex=0.6,
            sizey=min(pad * 0.6, 10.0),
            xanchor="center",
            yanchor="bottom",
            layer="above"
        )
    )
fig.update_layout(
    height=480,
    margin=dict(l=0, r=0, t=40, b=20),
    showlegend=False,
    yaxis=dict(range=[0, y_max + pad]),
    title=dict(text=title_text, x=0.5, xanchor='center'),
    font=dict(size=14)
)
if HAS_EVENTS:
    # plotly_events renders the chart and returns click events
    try:
        selected = plotly_events(
            fig,
            click_event=True,
            hover_event=False,
            select_event=False,
            keep_clicks=False,
            override_height=480,
            override_width=None,
        )
        if selected:
            from urllib.parse import urlencode
            # Prefer x (team name); some versions provide pointIndex as well
            team_clicked = selected[0].get("x")
            if not team_clicked:
                idx = selected[0].get("pointIndex")
                if idx is not None and 0 <= idx < len(res):
                    team_clicked = res.iloc[idx]["Team"]
            if team_clicked:
                # Build redirect URL with current filters
                teams_lookup = {t["displayName"]: t for t in teams}
                clicked = teams_lookup.get(team_clicked, {})
                slug = (clicked.get("nickname") or str(team_clicked)).lower()
                params = {"team": slug, "play": play, "compare": compare, "start": start, "end": end}
                url = f"/?{urlencode(params)}"
                st.markdown(f"<meta http-equiv='refresh' content='0; url={url}'>", unsafe_allow_html=True)
    except Exception:
        st.plotly_chart(fig, use_container_width=True)
else:
    st.plotly_chart(fig, use_container_width=True)

## End of page


