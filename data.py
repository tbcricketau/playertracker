import csv
from pathlib import Path

import streamlit as st

DATA_PATH = Path(__file__).parent / "data" / "aus_odi_player_career.csv"

NUMERIC_COLS = {
    "career_match_num",
    # per-match bowling (needed for block aggregation)
    "bowl_balls", "bowl_runs", "bowl_wkts",
    # career-to-date metrics (needed for career progression page)
    "ctd_bat_avg", "ctd_bat_sr", "ctd_bat_bpd", "ctd_bat_runs",
    "ctd_bowl_avg", "ctd_bowl_econ", "ctd_bowl_sr", "ctd_bowl_wkts",
}


@st.cache_data
def load_data():
    if not DATA_PATH.exists():
        return []
    rows = []
    with open(DATA_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            for col in NUMERIC_COLS:
                val = row.get(col, "")
                row[col] = float(val) if val != "" else None
            rows.append(row)
    return rows


def get_all_players(rows):
    return sorted({r["player_name"] for r in rows})


# ICC Full Members (excl. Australia) + Associates with permanent ODI status
_PRIORITY_OPPONENTS = {
    "Afghanistan", "Bangladesh", "England", "India", "Ireland",
    "New Zealand", "Pakistan", "South Africa", "Sri Lanka",
    "West Indies", "Zimbabwe",
    "Netherlands", "Scotland", "Namibia", "Oman",
    "Papua New Guinea", "Nepal", "United Arab Emirates", "USA",
}


def get_opponents(rows):
    """Return all opponents with Full Members / ODI nations first, then rest."""
    all_opp = {r["opponent"] for r in rows if r.get("opponent")}
    priority = sorted(o for o in all_opp if o in _PRIORITY_OPPONENTS)
    others   = sorted(o for o in all_opp if o not in _PRIORITY_OPPONENTS)
    return priority + others


def show_debut_table(rows, selected_players):
    """Render debut info as a markdown table (avoids pandas/st.dataframe)."""
    seen = {}
    for r in rows:
        name = r["player_name"]
        if name in selected_players and name not in seen and r.get("career_match_num") == 1.0:
            # debut_date column added in a later ETL run; fall back to match_date
            date = r.get("debut_date") or r.get("match_date", "—")
            seen[name] = (date, r.get("debut_age"), r.get("age_at_10"), r.get("age_at_20"))

    if not seen:
        return

    import streamlit as st
    body = ""
    for p in selected_players:
        if p in seen:
            date, age, age_10, age_20 = seen[p]
            def _fmt(v): return v if v is not None else "—"
            body += (
                f"<tr><td>{p}</td><td>{date}</td>"
                f"<td>{_fmt(age)}</td><td>{_fmt(age_10)}</td><td>{_fmt(age_20)}</td></tr>"
            )

    st.markdown(
        f"""<table style="font-size:11px; width:100%; border-collapse:collapse;">
  <thead><tr style="border-bottom:1px solid #444;">
    <th style="text-align:left; padding:3px 8px;">Player</th>
    <th style="text-align:left; padding:3px 8px;">Debut date</th>
    <th style="text-align:left; padding:3px 8px;">Debut age</th>
    <th style="text-align:left; padding:3px 8px;">Age at match 10</th>
    <th style="text-align:left; padding:3px 8px;">Age at match 20</th>
  </tr></thead>
  <tbody>{body}</tbody>
</table>""",
        unsafe_allow_html=True,
    )
