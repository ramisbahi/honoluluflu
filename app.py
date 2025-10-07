import streamlit as st
import pandas as pd
import plotly.express as px
from typing import Optional
from datetime import datetime, timedelta
from dateutil import tz as dateutil_tz

from hf.espn import LIONS_TEAM_ID, get_teams
from hf.flu import compute_honolulu_flu, summarize_percentage
from hf.theme import kpi_style, LIONS_COLORS


st.set_page_config(
    page_title="Honolulu Flu — Single Team",
    page_icon="🦁",
    layout="wide",
)

st.markdown(kpi_style(), unsafe_allow_html=True)

# Larger typography for main page metrics and tables
st.markdown(
    """
    <style>
    div[data-testid="stMetricValue"] { font-size: 2.2rem; }
    div[data-testid="stMetricLabel"] { font-size: 1.05rem; }
    /* Make dataframe text larger */
    div[data-testid='stDataFrame'] * { font-size: 1.45rem; }
    /* Ensure AG Grid cells/headers scale up */
    div[data-testid='stDataFrame'] .ag-cell,
    div[data-testid='stDataFrame'] .ag-header-cell,
    div[data-testid='stDataFrame'] .ag-header-group-cell { font-size: 1.45rem; }
    /* Reduce extra cell padding for tighter fit */
    div[data-testid='stDataFrame'] .st-ag-theme * { line-height: 1.3; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Smart caching: Eastern time and refresh policy
EASTERN = dateutil_tz.gettz("US/Eastern")

def should_refresh(last_fetched: Optional[datetime]) -> bool:
    now = datetime.now(EASTERN)
    if not last_fetched:
        return True
    if now - last_fetched > timedelta(hours=6):
        return True
    # Mon/Thu/Sat/Sun late-night post-game windows
    if now.weekday() in [0, 3, 5, 6] and now.hour >= 23:
        return True
    # Sunday smart windows: late afternoon games end ~4:30-5 ET
    if now.weekday() == 6 and ((now.hour == 16 and now.minute >= 35) or (now.hour == 17 and now.minute <= 15)):
        return True
    # Sunday primetime window around 8-9pm ET
    if now.weekday() == 6 and (now.hour in [20, 21]):
        return True
    # Sunday post-SNF wrap after 11:30pm ET
    if now.weekday() == 6 and (now.hour > 23 or (now.hour == 23 and now.minute >= 30)):
        return True
    return False

teams = get_teams()
id_to_name = {t["id"]: t["displayName"] for t in teams}
name_to_id = {t["displayName"]: t["id"] for t in teams}
slug_to_id = {t["nickname"].lower(): t["id"] for t in teams}
id_to_slug = {t["id"]: t["nickname"].lower() for t in teams}

# URL param helpers (compatible with older/newer Streamlit)
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

with st.sidebar:
    st.subheader("Team")
    team_names = sorted([t["displayName"] for t in teams])
    qp_team = _get_qp("team", id_to_slug.get(LIONS_TEAM_ID, "lions"))
    qp_team_id = slug_to_id.get(qp_team, LIONS_TEAM_ID)
    default_name = id_to_name.get(qp_team_id, "Detroit Lions")
    subject_team_name = st.selectbox("Select team", options=team_names, index=team_names.index(default_name) if default_name in team_names else 0, key="team_select")
    subject_team_id = name_to_id.get(subject_team_name, LIONS_TEAM_ID)

title_icon = "🦁" if subject_team_id == LIONS_TEAM_ID else "🏈"
accent = next((f"#{t['color']}" for t in teams if t["id"] == subject_team_id and t.get("color")), "#0076B6")
st.title(f"{title_icon} Honolulu Flu Tracker: Do You Believe?")
st.markdown(f"How NFL teams fare the week/game after facing the <b><span style='color:{accent}'>{subject_team_name}</span></b>.", unsafe_allow_html=True)
st.caption("Designed by Rami Sbahi. @RamiSbahi on X")

with st.sidebar:
    st.subheader("Filters")

    play_options = ["play", "beat"]
    play_qp = _get_qp("play", "play")
    play_mode = st.selectbox(
        f"{subject_team_name} games to include",
        options=play_options,
        index=play_options.index(play_qp) if play_qp in play_options else 0,
        format_func=lambda v: (f"{subject_team_name} beat opponent" if v == "beat" else f"All {subject_team_name} games"),
        help=f"Choose whether to only include games {subject_team_name} won, or all games.",
        key="play_select",
    )
    follow_mode = st.selectbox(
        "Define 'following game' as",
        options=["week", "game"],
        index=["week", "game"].index(_get_qp("compare", "week")),
        format_func=lambda v: "Next NFL week" if v == "week" else "Next played game",
        help="Next NFL week accounts for byes; Next played game ignores byes.",
        key="compare_select",
    )

    season_options = [2025, 2024, 2023, 2022, 2021]
    start_default = int(_get_qp("start", "2024"))
    end_default = int(_get_qp("end", "2025"))
    start_season = st.selectbox("From season", options=season_options, index=season_options.index(start_default) if start_default in season_options else 1, key="start_select")
    end_season = st.selectbox("Through season", options=season_options, index=season_options.index(end_default) if end_default in season_options else 0, key="end_select")

    if end_season < start_season:
        st.error("End season must be ≥ start season")
    seasons = list(range(start_season, end_season + 1)) if end_season >= start_season else []
    _set_qps({
        "team": id_to_slug.get(subject_team_id, qp_team),
        "play": play_mode,
        "compare": follow_mode,
        "start": start_season,
        "end": end_season,
    })

@st.cache_data(ttl=0, show_spinner=False)
def _cached_flu(_seasons, _play_mode, _follow_mode, _team_id):
    return compute_honolulu_flu(seasons=_seasons, play_mode=_play_mode, follow_mode=_follow_mode, subject_team_id=_team_id)

@st.cache_data
def _get_last_fetch_time():
    return datetime.now(EASTERN)

error_message = None
if seasons:
    try:
        # Smart refresh: clear cache after game windows / 6h
        last_fetched = st.session_state.get("last_fetched")
        if should_refresh(last_fetched):
            st.cache_data.clear()
            st.session_state["last_fetched"] = datetime.now(EASTERN)
        with st.spinner("Loading games..."):
            rows = _cached_flu(tuple(seasons), play_mode, follow_mode, subject_team_id)
    except Exception as e:
        rows = []
        error_message = str(e)
else:
    rows = []

def _format_week_label(week_text: Optional[str], week_num: Optional[int]) -> str:
    if not week_text:
        return str(week_num) if week_num is not None else "—"
    wt = week_text.lower()
    if "wild" in wt or "wildcard" in wt:
        return "WC"
    if "divisional" in wt:
        return "D"
    if "conference" in wt or "championship" in wt:
        return "C"
    if "super" in wt or "superbowl" in wt:
        return "SB"
    return str(week_num) if week_num is not None else "—"

# Human-friendly week text for display (regular week or playoff round)
def _human_week_text(label: Optional[object]) -> str:
    if label is None or (isinstance(label, str) and label.strip() == ""):
        return ""
    mapping = {"WC": "Wildcard", "D": "Divisional", "C": "Conference", "SB": "Super Bowl"}
    if isinstance(label, str):
        up = label.upper()
        if up in mapping:
            return mapping[up]
        if label.isdigit():
            try:
                return f"Week {int(label)}"
            except Exception:
                return ""
        return ""
    if isinstance(label, (int, float)) and pd.notna(label):
        try:
            return f"Week {int(label)}"
        except Exception:
            return ""
    return ""

df = pd.DataFrame([
    {
        "Season": r.season,
        "Week": _format_week_label(getattr(r, "week_label", None), r.week),
        "Date": r.date,
        "Opponent": r.lions_vs_label.replace("@ ", "@ ").replace("vs ", "vs "),
        "Team Result": getattr(r, "lions_result", None),
        "Team Score": getattr(r, "lions_team_score", None),
        "Opp Score": getattr(r, "lions_opp_score", None),
        "Opp Next Week": _format_week_label(getattr(r, "opp_next_week_label", None), getattr(r, "opp_next_week", None)),
        "Opp Next Date": r.opp_next_date,
        "Opp Next Result": getattr(r, "opp_next_result", None),
        "Opp Next Opponent": getattr(r, "opp_next_opp_name", None),
        "Opp Next Is Home": getattr(r, "opp_next_is_home", None),
        "Opp Next Score": getattr(r, "opp_next_team_score", None),
        "Opp Next Opp Score": getattr(r, "opp_next_opp_score", None),
        "Opp Next After Bye": getattr(r, "opp_next_after_bye", False),
        "Opp Next Cross Season": getattr(r, "opp_next_cross_season", False),
        "Honolulu Flu": ("Yes" if getattr(r, "honolulu_flu_loss", None) else ("No" if getattr(r, "honolulu_flu_loss", None) is not None else "—")),
    }
    for r in rows
])

# Friendlier formatted columns and opponent filter before computing KPIs
if not df.empty:
    # Sort by Lions game date (most recent first)
    df["SortTs"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.sort_values(["SortTs"], ascending=[False])
    df = df.drop(columns=["SortTs"])  

    # Ensure seasons render without thousand separators in charts and tables
    df["Season Label"] = df["Season"].astype(str)

    def _derive_result(res, a, b):
        if pd.isna(res) or res is None:
            if a is not None and b is not None and not pd.isna(a) and not pd.isna(b):
                try:
                    ai, bi = int(a), int(b)
                    if ai > bi:
                        return "W"
                    if ai < bi:
                        return "L"
                    return "T"
                except Exception:
                    return None
        return res

    def _fmt_lions(row):
        res = row.get("Team Result")
        a = row.get("Team Score")
        b = row.get("Opp Score")
        res = _derive_result(res, a, b)
        if pd.isna(res) or res is None or a is None or b is None or pd.isna(a) or pd.isna(b):
            # Pending/scheduled game without scores
            # Show the scheduled opponent and week text if available
            wk_text = _human_week(wk_label)
            wk_suffix = f" ({wk_text})" if wk_text else ""
            return f"Scheduled{opp_s}{wk_suffix}{year_suffix}" if opp_s else "—"
        return f"{res} {int(a)}–{int(b)}"

    def _fmt_next(row):
        # Bye case (next NFL week only)
        if follow_mode == "week" and row.get("Opp Next After Bye") and (pd.isna(row.get("Opp Next Result")) or row.get("Opp Next Result") is None):
            return "Bye"
        res = row.get("Opp Next Result")
        a = row.get("Opp Next Score")
        b = row.get("Opp Next Opp Score")
        res = _derive_result(res, a, b)
        opp = row.get("Opp Next Opponent")
        cross = row.get("Opp Next Cross Season", False)
        wk_label = row.get("Opp Next Week")
        if pd.isna(res) or res is None or a is None or b is None or pd.isna(a) or pd.isna(b):
            # Pending future game: show opponent and home/away
            if isinstance(opp, str) and opp:
                ha = " vs " if bool(row.get("Opp Next Is Home")) else " @ "
                wk_text = _human_week_text(wk_label)
                wk_suffix = f" ({wk_text})" if wk_text else ""
                return f"TBD{ha}{opp}{wk_suffix}"
            return "—"
        ha_played = " vs " if bool(row.get("Opp Next Is Home")) else " @ "
        opp_s = f"{ha_played}{opp}" if isinstance(opp, str) and opp else ""
        year_suffix = f" ({int(min(seasons) + 1)})" if cross and seasons else ""
        wk_text = _human_week_text(wk_label)
        wk_suffix = f" ({wk_text})" if wk_text else ""
        return f"{res} {int(a)}–{int(b)}{opp_s}{wk_suffix}{year_suffix}"

    df["Team Outcome"] = df.apply(_fmt_lions, axis=1)
    df["Next Outcome"] = df.apply(_fmt_next, axis=1)
    df["Flu?"] = df["Honolulu Flu"].map({"Yes": "🦠 Yes", "No": "No", "—": "—"})

    # Column tooltips configured below

with st.sidebar:
    pass

# KPIs computed from filtered data
if not df.empty:
    # Build Opp Next Outcome early for filtering in KPIs
    tmp = df.copy()
    tmp["Opp Next Outcome"] = tmp.apply(_fmt_next, axis=1)
    considered = tmp[tmp["Honolulu Flu"].isin(["Yes", "No"])].copy()
    considered = considered[considered["Opp Next Outcome"] != "Bye"]
    losses = int((considered["Honolulu Flu"] == "Yes").sum())
    total = int(len(considered))
    pct = (losses / total * 100.0) if total else 0.0
else:
    losses = 0
    total = 0
    pct = 0.0

col1, col2, col3 = st.columns([1, 1, 1])
with col1:
    st.metric(label="Honolulu Flu Losses", value=losses)
with col2:
    st.metric(label="Total Considered", value=total)
with col3:
    st.metric(label="Honolulu Flu %", value=f"{(pct or 0):.1f}%")

st.divider()

st.subheader("Games")
st.caption(
    f"Showing {len(df)} {subject_team_name} games • Include: "
    f"{subject_team_name + ' beat' if play_mode == 'beat' else 'All games'}"
    f" • Following: {'Next week' if follow_mode == 'week' else 'Next played game'}"
    f" • Seasons: {min(seasons) if seasons else ''}–{max(seasons) if seasons else ''}"
)
if error_message:
    st.error(f"Failed to fetch data: {error_message}")

if not df.empty:
    display_cols = ["Season Label", "Week", "Opponent", "Team Outcome", "Opp Next Outcome", "Flu?"]
    df = df.rename(columns={"Next Outcome": "Opp Next Outcome"})
    st.dataframe(
        df[display_cols],
        use_container_width=True,
        hide_index=True,
        column_config={
            "Week": st.column_config.TextColumn("Week"),
            "Opp Next Outcome": st.column_config.TextColumn(
                "Opp Next Outcome",
                help="If the Lions beat a team in the playoffs, we show that team's first game next regular season (suffix with year). If the Lions lost, we show that team's next playoff game this season. In 'Next NFL week' mode, a bye shows as 'Bye' and is excluded from stats.",
            ),
        },
    )
else:
    st.info("No games to display for the selected filters.")

if not df.empty:
    plot_df = df[df["Honolulu Flu"].isin(["Yes", "No"])].copy()
    # Exclude "Bye" rows from considered stats/charts
    plot_df = plot_df[plot_df["Opp Next Outcome"] != "Bye"]
    plot_df["is_flu"] = plot_df["Honolulu Flu"] == "Yes"
    fig = px.histogram(
        plot_df,
        x="Season",
        color="is_flu",
        barmode="group",
        category_orders={"Season": sorted(plot_df["Season"].unique().tolist())},
        color_discrete_map={True: accent, False: LIONS_COLORS["silver"]},
        text_auto=True,
    )
    fig.update_layout(height=360, showlegend=False, margin=dict(l=0, r=0, t=10, b=0), xaxis_tickformat="d", font=dict(size=14))
    st.plotly_chart(fig, use_container_width=True)

    # Pie chart summary
    pie_df = plot_df.groupby("Honolulu Flu").size().reset_index(name="count")
    pie_fig = px.pie(
        pie_df,
        names="Honolulu Flu",
        values="count",
        color="Honolulu Flu",
        color_discrete_map={"Yes": accent, "No": LIONS_COLORS["silver"]},
    )
    pie_fig.update_traces(textinfo='percent+label')
    pie_fig.update_layout(height=360, margin=dict(l=0, r=0, t=10, b=0), font=dict(size=14))
    st.plotly_chart(pie_fig, use_container_width=True)

st.caption("Source: ESPN public APIs. This tool is unofficial and for fun.")




st.markdown(
    """
    <hr style="margin-top:2em; margin-bottom:1em;">
    <div style="text-align:center; font-size:0.9em;">
      <a href="https://github.com/ramisbahi/honoluluflu" target="_blank" style="color:white; text-decoration:none;">
        ⭐ View source on GitHub
      </a>
    </div>
    """,
    unsafe_allow_html=True
)