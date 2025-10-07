from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple

from dateutil import parser as dateparser

from .espn import get_team_schedule


FollowMode = Literal["week", "game"]
PlayMode = Literal["play", "beat"]


@dataclass
class GameRow:
    season: int
    week: Optional[int]
    week_label: Optional[str]  # "Week 1", "Divisional Round", etc
    date: str
    is_home: bool
    opp_id: str
    opp_name: str
    lions_result: Optional[str]  # W/L/T
    lions_team_score: Optional[int]
    lions_opp_score: Optional[int]
    opp_next_date: Optional[str]
    opp_next_week: Optional[int]
    opp_next_week_label: Optional[str]
    opp_next_result: Optional[str]  # W/L/T from opponent perspective
    opp_next_opp_name: Optional[str]
    opp_next_team_score: Optional[int]
    opp_next_opp_score: Optional[int]
    opp_next_after_bye: bool = False
    opp_next_cross_season: bool = False
    opp_next_is_home: Optional[bool] = None

    @property
    def lions_vs_label(self) -> str:
        return ("vs " if self.is_home else "@ ") + self.opp_name

    @property
    def honolulu_flu_loss(self) -> Optional[bool]:
        if self.opp_next_result is None:
            return None
        return self.opp_next_result == "L"


def _parse_iso(date_str: Optional[str]) -> Optional[int]:
    if not date_str:
        return None
    try:
        return int(dateparser.parse(date_str).timestamp())
    except Exception:
        return None


def _pick_next_week_game(opponent_schedule: List[Dict[str, Any]], target_week: int) -> Optional[Dict[str, Any]]:
    # Only return a regular-season game in the immediate next week
    for row in opponent_schedule:
        if row.get("season_type") != 2:
            continue
        if row.get("week") == target_week:
            return row
    return None


def _pick_next_game_after(opponent_schedule: List[Dict[str, Any]], lions_game_ts: int) -> Optional[Dict[str, Any]]:
    best: Optional[Tuple[int, Dict[str, Any]]] = None
    for row in opponent_schedule:
        ts = _parse_iso(row.get("date"))
        if ts is None:
            continue
        if ts > lions_game_ts:
            if best is None or ts < best[0]:
                best = (ts, row)
    return best[1] if best else None


def _pick_next_game_after_with_filters(
    opponent_schedule: List[Dict[str, Any]],
    after_ts: int,
    season: Optional[int] = None,
    season_type: Optional[int] = None,
) -> Optional[Dict[str, Any]]:
    best: Optional[Tuple[int, Dict[str, Any]]] = None
    for row in opponent_schedule:
        if season is not None and row.get("season") != season:
            continue
        if season_type is not None and row.get("season_type") != season_type:
            continue
        ts = _parse_iso(row.get("date"))
        if ts is None or ts <= after_ts:
            continue
        if best is None or ts < best[0]:
            best = (ts, row)
    return best[1] if best else None


def compute_honolulu_flu(seasons: Iterable[int], play_mode: PlayMode, follow_mode: FollowMode, subject_team_id: str) -> List[GameRow]:
    rows: List[GameRow] = []

    for season in seasons:
        subject_schedule = [
            r for r in get_team_schedule(subject_team_id, season)
            if r.get("season_type") in (2, 3)
        ]
        for game in subject_schedule:
            if not game.get("completed"):
                continue
            if play_mode == "beat" and game.get("team_result") != "W":
                continue

            opp_id = str(game.get("opp_id"))
            opp_name = str(game.get("opp_name") or "")
            lions_game_ts = _parse_iso(game.get("date")) or 0

            opp_sched = get_team_schedule(opp_id, season)

            next_row: Optional[Dict[str, Any]] = None
            after_bye = False
            cross_season = False

            is_playoffs_game = game.get("season_type") == 3
            lions_result = game.get("team_result")

            if is_playoffs_game:
                if lions_result == "L":
                    # Opponent continues in playoffs this season: pick their next postseason game
                    next_row = _pick_next_game_after_with_filters(opp_sched, lions_game_ts, season=season, season_type=3)
                else:
                    # Opponent eliminated: first regular-season game of next season
                    next_sched = get_team_schedule(opp_id, season + 1)
                    next_sched_sorted = sorted(
                        [r for r in next_sched if r.get("season_type") == 2],
                        key=lambda r: _parse_iso(r.get("date")) or 0,
                    )
                    next_row = next_sched_sorted[0] if next_sched_sorted else None
                    cross_season = next_row is not None
            else:
                if follow_mode == "week":
                    week = game.get("week")
                    next_row = _pick_next_week_game(opp_sched, (week or 0) + 1) if week is not None else None
                    if next_row is None:
                        # Check if opponent has any later game in same season (reg or post)
                        any_later_same_season = _pick_next_game_after_with_filters(opp_sched, lions_game_ts, season=season) is not None
                        if any_later_same_season:
                            # It's a BYE; do not fallback and do not cross-season
                            after_bye = True
                        else:
                            # Truly last game of the season; use next season first regular-season game
                            next_sched = get_team_schedule(opp_id, season + 1)
                            next_sched_sorted = sorted(
                                [r for r in next_sched if r.get("season_type") == 2],
                                key=lambda r: _parse_iso(r.get("date")) or 0,
                            )
                            next_row = next_sched_sorted[0] if next_sched_sorted else None
                            cross_season = next_row is not None
                else:
                    next_row = _pick_next_game_after(opp_sched, lions_game_ts)

                    # If still none, look at next season's first game of any type
                    if next_row is None:
                        next_sched = get_team_schedule(opp_id, season + 1)
                        next_sched_sorted = sorted(next_sched, key=lambda r: _parse_iso(r.get("date")) or 0)
                        next_row = next_sched_sorted[0] if next_sched_sorted else None
                        cross_season = next_row is not None

            rows.append(
                GameRow(
                    season=season,
                    week=game.get("week"),
                    week_label=game.get("week_text"),
                    date=str(game.get("date")),
                    is_home=bool(game.get("is_home")),
                    opp_id=opp_id,
                    opp_name=opp_name,
                    lions_result=game.get("team_result"),
                    lions_team_score=game.get("team_score"),
                    lions_opp_score=game.get("opp_score"),
                    opp_next_date=(next_row or {}).get("date"),
                    opp_next_week=(next_row or {}).get("week"),
                    opp_next_week_label=(next_row or {}).get("week_text"),
                    opp_next_result=(next_row or {}).get("team_result"),
                    opp_next_opp_name=(next_row or {}).get("opp_name"),
                    opp_next_team_score=(next_row or {}).get("team_score"),
                    opp_next_opp_score=(next_row or {}).get("opp_score"),
                    opp_next_after_bye=after_bye,
                    opp_next_cross_season=cross_season,
                    opp_next_is_home=((next_row or {}).get("is_home") if next_row else None),
                )
            )

    return rows


def summarize_percentage(rows: List[GameRow]) -> Tuple[int, int, Optional[float]]:
    considered = [r for r in rows if r.honolulu_flu_loss is not None]
    total = len(considered)
    losses = sum(1 for r in considered if r.honolulu_flu_loss)
    pct = (losses / total * 100.0) if total > 0 else None
    return losses, total, pct


