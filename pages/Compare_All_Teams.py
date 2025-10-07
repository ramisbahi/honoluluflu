import streamlit as st
import pandas as pd
import plotly.express as px

from hf.espn import get_teams
from hf.flu import compute_honolulu_flu

st.set_page_config(page_title="Honolulu Flu — Compare Teams", page_icon="📊", layout="wide")

teams = get_teams()
team_id_name = {t["id"]: t["displayName"] for t in teams}

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
    key="play_all_select",
)
compare = st.sidebar.selectbox(
    "Following game is",
    options=["week", "game"],
    index=["week", "game"].index(_get_qp("compare", "week")),
    format_func=lambda v: ("Next NFL week" if v == "week" else "Next played game"),
    key="compare_all_select",
)
season_options = [2025, 2024, 2023, 2022, 2021]
start = st.sidebar.selectbox("From season", options=season_options, index=season_options.index(int(_get_qp("start", "2024"))), key="start_all_select")
end = st.sidebar.selectbox("Through season", options=season_options, index=season_options.index(int(_get_qp("end", "2025"))), key="end_all_select")
if end < start:
    st.sidebar.error("End season must be ≥ start season")
seasons = list(range(start, end + 1)) if end >= start else []
_set_qps({"play": play, "compare": compare, "start": start, "end": end})

st.title("📊 Honolulu Flu — All Teams")
st.caption("Comparison of Honolulu Flu % across teams (same filters as main page).")

rows = []
with st.spinner("Computing Honolulu Flu across all teams..."):
    for t in teams:
        sid = t["id"]
        name = t["displayName"]
        try:
            r = compute_honolulu_flu(seasons=tuple(seasons), play_mode=play, follow_mode=compare, subject_team_id=sid)
        except Exception:
            r = []
        df = pd.DataFrame([
            {"flu": (1 if (getattr(x, "honolulu_flu_loss", None) is True) else (0 if getattr(x, "honolulu_flu_loss", None) is False else None)), "opp_next_result": getattr(x, "opp_next_result", None)} for x in r
        ])
        # Exclude byes/NA from denominator
        considered = df[df["opp_next_result"].isin(["W", "L", "T"])]
        total = len(considered)
        pct = (considered["flu"].sum() / total * 100.0) if total else 0.0
        rows.append({"Team": name, "Flu %": pct, "Total": total})

res = pd.DataFrame(rows).sort_values(["Flu %"], ascending=[False])
st.dataframe(res, use_container_width=True, hide_index=True)

fig = px.bar(res, x="Team", y="Flu %")
fig.update_layout(height=460, margin=dict(l=0, r=0, t=10, b=0))
st.plotly_chart(fig, use_container_width=True)


