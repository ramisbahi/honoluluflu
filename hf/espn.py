from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, List, Optional

import httpx


ESPN_TEAM_SCHEDULE = (
    "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/{team_id}/schedule?season={season}"
)


def _safe_int(value: Optional[str]) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def _coerce_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def _parse_game(team_id: str, event: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    comp = (event.get("competitions") or [{}])[0]
    competitors = comp.get("competitors") or []
    if len(competitors) < 2:
        return None

    team_side = None
    opp_side = None
    for c in competitors:
        if c.get("team", {}).get("id") == team_id:
            team_side = c
        else:
            opp_side = c

    if not team_side or not opp_side:
        return None

    status = comp.get("status", {}).get("type", {})
    completed = bool(status.get("completed"))

    def _extract_score(score_field: Any) -> Optional[int]:
        # Handles ESPN variants: "34", 34, {"value": 34.0, "displayValue": "34"}
        if score_field is None:
            return None
        if isinstance(score_field, (int, float)):
            try:
                return int(score_field)
            except Exception:
                return None
        if isinstance(score_field, str):
            return _safe_int(score_field)
        if isinstance(score_field, dict):
            val = score_field.get("value")
            if isinstance(val, (int, float)):
                return int(val)
            disp = score_field.get("displayValue")
            return _safe_int(disp) if disp is not None else None
        return None

    team_score = _extract_score(team_side.get("score"))
    opp_score = _extract_score(opp_side.get("score"))

    result = None
    if completed:
        # Prefer explicit 'winner' boolean if present
        if team_side.get("winner") is True:
            result = "W"
        elif opp_side.get("winner") is True:
            result = "L"
        elif team_score is not None and opp_score is not None:
            result = "W" if team_score > opp_score else ("L" if team_score < opp_score else "T")

    season = _coerce_int((event.get("season") or {}).get("year"))
    # On site API, seasonType is separate
    season_type = _coerce_int((event.get("seasonType") or {}).get("type") or (event.get("season") or {}).get("type"))
    week = _coerce_int((event.get("week") or {}).get("number"))
    week_text = (event.get("week") or {}).get("text")

    return {
        "event_id": event.get("id"),
        "date": event.get("date"),
        "completed": completed,
        "season": season,
        "season_type": season_type,
        "week": week,
        "week_text": week_text,
        "is_home": bool(team_side.get("homeAway") == "home"),
        "team_id": team_id,
        "team_score": team_score,
        "opp_id": (opp_side.get("team") or {}).get("id"),
        "opp_name": (opp_side.get("team") or {}).get("displayName"),
        "opp_score": opp_score,
        "team_result": result,
    }


@lru_cache(maxsize=128)
def get_team_schedule(team_id: str, season: int) -> List[Dict[str, Any]]:
    """Fetch regular season + postseason games for a team in a given season."""
    parsed = []
    
    # Fetch regular season (type 2) and postseason (type 3)
    for season_type in [2, 3]:
        url = ESPN_TEAM_SCHEDULE.format(team_id=team_id, season=season) + f"&seasontype={season_type}"
        with httpx.Client(timeout=20) as client:
            try:
                resp = client.get(url)
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                continue
        
        events = data.get("events") or []
        for ev in events:
            row = _parse_game(team_id, ev)
            if row:
                parsed.append(row)
    
    parsed.sort(key=lambda r: (r.get("date") or ""))
    return parsed


LIONS_TEAM_ID = "8"  # ESPN team id for Detroit Lions


@lru_cache(maxsize=5)
def get_teams() -> List[Dict[str, Any]]:
    """Return a list of NFL teams with id, displayName, abbreviation, nickname."""
    url = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams"
    with httpx.Client(timeout=20) as client:
        resp = client.get(url)
        resp.raise_for_status()
        data = resp.json()

    teams: List[Dict[str, Any]] = []
    for g in (data.get("sports") or [{}])[0].get("leagues", [{}])[0].get("teams", []) or []:
        t = g.get("team") or {}
        teams.append({
            "id": t.get("id"),
            "displayName": t.get("displayName"),
            "abbreviation": t.get("abbreviation"),
            "nickname": t.get("nickname"),
        })
    return teams

