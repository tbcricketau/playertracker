# Player Career Tracker

Streamlit app for **Australian ODI career progression** — one row per player per match,
so you can compare career trajectories ("where was Hazlewood after his 10th ODI vs where
Bartlett was after his 10th"). Scope: `match_length_id = '1'` (50-over), Australia Men
(`team_id = '1004'`), from ~2005 onwards.

## Run locally

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# 1. Build the career CSV from the warehouse (writes data/aus_odi_player_career.csv)
.\.venv\Scripts\python.exe scripts\build_player_career.py        # --since YYYY-MM-DD to override cutoff

# 2. Run the app
.\.venv\Scripts\python.exe -m streamlit run app.py
```

`app.py` is the entry point (`st.navigation` → Career Progression / Block Analysis pages).

## Data

- **Live data** comes from the Azure SQL warehouse via `cricket_core.warehouse`
  (non-interactive MSAL auth); schema is `cricket_core.config.DATA_SCHEMA`.
- `scripts/build_player_career.py` produces `data/aus_odi_player_career.csv`, which the app
  reads. That CSV is **gitignored** (rebuildable, and schema-specific — regenerate after a
  data drop / `DATA_SCHEMA` change). Run the build step before first launch.
- Self-contained — no dependency on the referencebuilder reference files.
- No pandas/numpy (parent house rules); uses `list[dict]` + the `csv` module.

> Note: `match_length_id = '1'` can include domestic 50-over matches alongside
> internationals — filter by the `series` column to isolate a specific competition.
