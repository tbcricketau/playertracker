# Player Career Tracker

Builds a CSV of Australian ODI player career progression from the Azure cricket database. One row per player per match, enabling career-trajectory comparisons like "where was Hazelwood after his 10th ODI vs where Bartlett was after his 10th."

## Scope

- Format: ODI / 1-Day (`match_length_id = '1'`)
- Team: Australia Men (`team_id = '1004'`)
- Date range: from April 2015 onwards (matches after the 2015 ICC World Cup final on 2015-03-29)
- Includes any match where Australia was team_a or team_b

**Note:** `match_length_id = '1'` may include domestic 50-over competitions alongside internationals. Filter by the `series` column to isolate specific competitions.

## Database

Same Azure SQL Server as `c:\Projects\livematchdashboard`. Credentials via environment variables:
- `app_id` — Azure AD app client ID
- `app_secret` — Azure AD app client secret

Connection comes from the shared package: `cricket_core.warehouse` (MSAL token auth + SSO
fallback). Warehouse guide: `../cricket-core/DATAWAREHOUSE.md` — read before any query.

- Schema: `cricket_core.config.DATA_SCHEMA` (re-exported via `config.py`)
- Australia Men team ID: `"1004"`
- `how_out` lookup: `lookup_type_id = 2806`
- `over` is a reserved SQL Server keyword — always use `D.[over]` in queries
- All values from `run_query_to_df` come back as Python strings; cast with `float(v)` /
  `int(v)` in try/except (**no pandas** — house rule, see parent CLAUDE.md)
- `bowler_dismissal` is a SQL BIT column → arrives as `"True"` or `"False"` (not 0/1); check with `str.lower().isin(["true", "1"])`
- `legal_ball` is the authoritative column for whether a delivery counts in the over (more reliable than `wide_runs == 0`)

## Running the script

```cmd
:: One-time venv setup (use py launcher; plain python is not on PATH system-wide)
py -3 -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt

:: Build the dataset (pulls from 2005 onwards by default)
python scripts/build_player_career.py

:: Optional: custom output path or date range
python scripts/build_player_career.py --out C:\path\to\custom.csv
python scripts/build_player_career.py --since 2010-01-01
```

Activate the venv once per terminal session; after that `python` and `streamlit` resolve from the venv automatically.

Output lands at `data/aus_odi_player_career.csv`.

## Running the Streamlit app

```cmd
.venv\Scripts\activate
streamlit run app.py
```

Opens in browser at http://localhost:8501. Requires the CSV to exist first (run the ETL script above).

## Output schema

One row per player per match. Players who didn't bat have NaN batting columns; players who didn't bowl have NaN bowling columns.

### Identity & match context

| Column | Description |
|--------|-------------|
| `player_id` | DB player identifier |
| `player_name` | Full name (first + surname) |
| `career_match_num` | 1 = first match in this dataset, 2 = second, etc. (sorted by match_date) |
| `match_id` | DB match identifier |
| `match_date` | Date of the match |
| `opponent` | Opposition team name |
| `venue` | Venue abbreviation |
| `series` | Series name |
| `aus_bat_innings` | Which innings Australia batted (1 or 2) |
| `aus_result` | `won` / `lost` / `tied` / `no_result` |
| `aus_runs` | Australia's total score |
| `aus_wkts` | Australia's wickets lost |
| `opp_runs` | Opposition's total score |
| `opp_wkts` | Opposition's wickets lost |

### Batting — this match (NaN if player didn't bat)

| Column | Description |
|--------|-------------|
| `bat_pos` | Batting position |
| `bat_runs` | Runs scored |
| `bat_balls` | Balls faced (legal deliveries only) |
| `bat_fours` | 4s scored |
| `bat_sixes` | 6s scored |
| `bat_sr` | Strike rate (runs/balls×100) |
| `bat_not_out` | 1 if not dismissed, 0 if out |
| `bat_how_out` | Dismissal type (e.g. "Caught", "Bowled") or "Not Out" |

### Batting — career to date (stats THROUGH this match)

Prefix `ctd_` = career-to-date, cumulative including this match.
At career_match_num=10, ctd_bowl_avg is the bowling average across all 10 matches.

| Column | Description |
|--------|-------------|
| `ctd_bat_innings` | Innings batted |
| `ctd_bat_not_outs` | Times not out |
| `ctd_bat_runs` | Total runs |
| `ctd_bat_balls` | Total balls faced |
| `ctd_bat_avg` | Batting average (runs / (innings − not_outs)) |
| `ctd_bat_sr` | Career strike rate |
| `ctd_bat_50s` | Half-centuries |
| `ctd_bat_100s` | Centuries |
| `ctd_bat_hs` | High score |

### Bowling — this match (NaN if player didn't bowl)

| Column | Description |
|--------|-------------|
| `bowl_pos` | Bowling rotation position |
| `bowl_overs` | Overs bowled (string, e.g. "9.3") |
| `bowl_balls` | Legal deliveries bowled |
| `bowl_runs` | Runs conceded (bat + wides + no-balls) |
| `bowl_wkts` | Wickets taken |
| `bowl_econ` | Economy rate |
| `bowl_dot_pct` | Dot ball percentage |
| `bowl_4w` | 1 if 4+ wickets in this innings |
| `bowl_5w` | 1 if 5+ wickets in this innings |

### Bowling — career to date (stats THROUGH this match)

| Column | Description |
|--------|-------------|
| `ctd_bowl_innings` | Innings bowled |
| `ctd_bowl_wkts` | Total wickets |
| `ctd_bowl_runs` | Total runs conceded |
| `ctd_bowl_balls` | Total balls bowled |
| `ctd_bowl_avg` | Bowling average (runs / wkts) |
| `ctd_bowl_econ` | Economy rate |
| `ctd_bowl_sr` | Bowling strike rate (balls / wkt) |
| `ctd_bowl_4w_count` | Number of 4-wicket hauls |
| `ctd_bowl_5w_count` | Number of 5-wicket hauls |

## Example analysis (stdlib — no pandas, house rule)

```python
import csv

with open("data/aus_odi_player_career.csv", newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))

# Compare Hazelwood vs Bartlett at the same career milestone
comp = [r for r in rows if r["career_match_num"] == "10"
        and r["player_name"] in ("Josh Hazelwood", "Xavier Bartlett")]
for r in comp:
    print(r["player_name"], r["ctd_bowl_wkts"], r["ctd_bowl_avg"], r["ctd_bowl_econ"])

# Career bowling-average progression for a player (plot with Plotly, lists directly)
haze = sorted((r for r in rows if r["player_name"] == "Josh Hazelwood"),
              key=lambda r: int(r["career_match_num"]))
xs = [int(r["career_match_num"]) for r in haze]
ys = [float(r["ctd_bowl_avg"]) for r in haze if r["ctd_bowl_avg"] not in ("", "None")]
```

## Known limitations

- `career_match_num` counts only from April 2015. Players like Hazelwood who debuted before 2015 will have truncated career histories — `career_match_num = 1` is their first *coded* ODI in this dataset, not their first ever ODI.
- Match result detection assumes both teams complete their innings. DLS-affected or abandoned matches may show `no_result` even if a winner was declared.
- Domestic 50-over competitions share `match_length_id = '1'`; filter by `series` to isolate international matches.

## Project files

```
playertracker/
├── CLAUDE.md                          ← this file
├── config.py                          ← team ID, date cutoff (DATA_SCHEMA from cricket_core)
├── requirements.txt                   ← starts with -e ../cricket-core
├── setup.ps1                          ← one-command env build
├── data/
│   └── aus_odi_player_career.csv      ← generated output (run the script)
└── scripts/
    └── build_player_career.py         ← main ETL script (warehouse via cricket_core)
```
