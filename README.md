# Honolulu Flu Tracker

Track how NFL teams perform the week/game after facing a selected team — the tongue‑in‑cheek “Honolulu Flu.” Default focuses on the Detroit Lions, but you can analyze any team, compare across all teams, and share filterable views via URL parameters.

## What is the “Honolulu Flu”?
A meme that teams often lose the week after playing the Detroit Lions. This app quantifies that idea: for each game vs the selected team, we look at the opponent’s next game (by NFL week or next played game) and compute how often they lose.

## Features
- Team selector (default: Detroit Lions) — works for any NFL team
- Filters (all preserved in URL so views are shareable):
  - Include: All games vs Team, or only games the Team won (Beat opponent)
  - Following game: Next NFL week (accounts for byes) or Next played game (ignores byes)
  - Season range: From season … Through season (regular + postseason are considered per logic below)
- Playoffs-aware logic
  - If the selected team loses a playoff game: opponent’s next playoff game (same season)
  - If the selected team wins a playoff game: opponent’s first regular‑season game next season (suffix shows the year)
- Bye handling (Next NFL week mode)
  - If the opponent doesn’t play the very next week but does later that season: show “Bye” and exclude from stats
  - Only use next season’s first game if the opponent had no later game that season (truly last game)
- Polished UI with metrics, a detailed table, and charts
- Second page: Compare all teams’ Honolulu Flu % with the same filters

## URL Parameters (shareable)
The app encodes current filters in the URL. Example:

```
?team=lions&play=play&compare=week&start=2024&end=2025
```

- `team`: team nickname slug (e.g., `lions`, `cardinals`, `vikings`)
- `play`: `play` (all games) or `beat` (only wins by the selected team)
- `compare`: `week` (next NFL week) or `game` (next played game)
- `start`: start season year (e.g., `2024`)
- `end`: end season year (e.g., `2025`)

The Compare page uses the same `play`, `compare`, `start`, and `end` URL parameters.

## Data Source
Public ESPN endpoints (no keys):
- Teams: `https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams`
- Team schedule (per season & season type):
  - Regular season: `.../teams/{id}/schedule?season=YYYY&seasontype=2`
  - Postseason: `.../teams/{id}/schedule?season=YYYY&seasontype=3`

The app merges regular + postseason schedules for each team so it can apply the playoff rules above.

## How the logic works (core rules)
For each game the selected team plays in the chosen seasons:
1. If Include = All games: use all games. If Include = Beat opponent: use only games the selected team won
2. Following game = Next NFL week
   - If the opponent plays in the immediate next NFL week: use that game
   - If the opponent does not play next week but has a later game the same season: mark “Bye” and exclude from stats
   - If the opponent has no later game the same season: use first regular‑season game of next season (suffix year)
3. Following game = Next played game
   - Use the opponent’s next chronological game (same season if possible, otherwise next season)
4. Playoffs
   - If the selected team lost a playoff game, we use the opponent’s next playoff game that same season
   - If the selected team won a playoff game, we use the opponent’s first regular‑season game in the next season (suffix the year)

The “Honolulu Flu %” is calculated as: losses ÷ (losses + wins + ties). “Bye” rows and any NA rows are excluded.

## Project Structure
```
.
├── app.py                         # Main Streamlit app (team view)
├── pages/
│   └── Compare_All_Teams.py       # All‑teams comparison view
├── hf/
│   ├── espn.py                    # ESPN API calls & parsing
│   ├── flu.py                     # Honolulu Flu computation logic
│   ├── theme.py                   # Colors & small style helpers
│   └── __init__.py
├── requirements.txt
└── .streamlit/config.toml         # Theme (Honolulu blue, etc.)
```

## Setup & Run
Requirements: Python 3.10+

```
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

- The app will open in your browser (default `http://localhost:8501`).
- The Compare page appears in the sidebar’s page selector or at `/Compare_All_Teams`.

## Deployment
- Streamlit Community Cloud: push this repo and deploy directly; it will install `requirements.txt` and run `streamlit run app.py`
- Any container/host that can run Python; expose port 8501 (or configured port)

## Notes & Caveats
- ESPN’s public endpoints have no guarantees; fields can vary and may change
- Schedules include upcoming (unscored) games; those display as “Scheduled …” in Opp Next Outcome
- “Bye” rows (week mode) are excluded from stats
- The Compare page computes each team’s percentage using the same filter set — it can take a few seconds on cold start (there’s a spinner)

## Credits
- Data: ESPN public APIs
- Designed by Rami Sbahi
- Built with Streamlit + Python
