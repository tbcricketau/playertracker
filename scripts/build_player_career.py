"""
Build Australian ODI player career progression CSV.

One row per player per match, with per-match stats and career-to-date (ctd_*)
stats accumulated in all PRIOR matches for that player.

This lets you compare players at the same career milestone:
    df[df["career_match_num"] == 10]   # all players' 10th match

Usage:
    python scripts/build_player_career.py [--out path/to/output.csv] [--since YYYY-MM-DD]

Output: data/aus_odi_player_career.csv
"""

import argparse
import csv
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import DATA_SCHEMA, AUS_TEAM_ID, ODI_MATCH_LENGTH_ID, ODI_CUTOFF_DATE
from cricket_core.warehouse import set_conn_cursor, run_query

OUTPUT_DEFAULT = Path(__file__).resolve().parent.parent / "data" / "aus_odi_player_career.csv"

def build_query(since_date):
    return f"""
SELECT
    D.match_id,
    CAST(M.match_date AS DATE)                                AS match_date,
    M.team_a_id,
    M.team_b_id,
    CASE WHEN M.team_a_id = '{AUS_TEAM_ID}'
         THEN TB.team_name ELSE TA.team_name END               AS opponent,
    V.abbreviation                                            AS venue,
    ISNULL(SR.name, '')                                       AS series,
    D.match_innings,
    D.team_batting_id,
    D.team_bowling_id,
    D.striker_id,
    ISNULL(PS.name,   '') + ' ' + ISNULL(PS.surname,   '')   AS striker_name,
    CAST(PS.date_of_birth   AS DATE)                          AS striker_dob,
    D.striker_batting_position,
    D.bowler_id,
    ISNULL(PBWL.name, '') + ' ' + ISNULL(PBWL.surname, '')   AS bowler_name,
    CAST(PBWL.date_of_birth AS DATE)                          AS bowler_dob,
    D.bowler_bowling_position,
    D.bat_score,
    D.wide_runs,
    D.noball_runs,
    D.bye_runs,
    D.legbye_runs,
    D.batter_out_id,
    D.bowler_dismissal,
    ISNULL(L_how_out.description, '')                         AS how_out,
    D.legal_ball
FROM [{DATA_SCHEMA}].[Deliveries]   AS D
JOIN [{DATA_SCHEMA}].[Matches]      AS M    ON D.match_id    = M.match_id
JOIN [{DATA_SCHEMA}].[Teams]        AS TA   ON M.team_a_id   = TA.team_id
JOIN [{DATA_SCHEMA}].[Teams]        AS TB   ON M.team_b_id   = TB.team_id
JOIN [{DATA_SCHEMA}].[Players]      AS PS   ON D.striker_id  = PS.player_id
JOIN [{DATA_SCHEMA}].[Players]      AS PBWL ON D.bowler_id   = PBWL.player_id
JOIN [{DATA_SCHEMA}].[Venues]       AS V    ON M.venue_id    = V.venue_id
LEFT JOIN [{DATA_SCHEMA}].[Series]  AS SR   ON M.series_id   = SR.series_id
LEFT JOIN [{DATA_SCHEMA}].[Lookups] AS L_how_out
    ON L_how_out.lookup_type_id = 2806 AND L_how_out.id = D.how_out_id
WHERE M.match_length_id = '{ODI_MATCH_LENGTH_ID}'
  AND M.match_date > '{since_date}'
  AND (M.team_a_id = '{AUS_TEAM_ID}' OR M.team_b_id = '{AUS_TEAM_ID}')
  AND M.coding_state_id <> 10
ORDER BY M.match_date, D.match_innings, D.[over], D.ball_in_over
"""

COL_ORDER = [
    "player_id", "player_name", "career_match_num", "debut_date", "debut_age", "age_at_10", "age_at_20",
    "match_id", "match_date", "opponent", "venue", "series",
    "aus_bat_innings", "aus_result",
    "aus_runs", "aus_wkts", "opp_runs", "opp_wkts",
    "bat_pos", "bat_runs", "bat_balls", "bat_fours", "bat_sixes",
    "bat_sr", "bat_not_out", "bat_how_out",
    "ctd_bat_innings", "ctd_bat_not_outs", "ctd_bat_runs", "ctd_bat_balls",
    "ctd_bat_avg", "ctd_bat_sr", "ctd_bat_bpd", "ctd_bat_50s", "ctd_bat_100s", "ctd_bat_hs",
    "bowl_pos", "bowl_overs", "bowl_balls", "bowl_runs", "bowl_wkts",
    "bowl_econ", "bowl_dot_pct", "bowl_4w", "bowl_5w",
    "ctd_bowl_innings", "ctd_bowl_wkts", "ctd_bowl_runs", "ctd_bowl_balls",
    "ctd_bowl_avg", "ctd_bowl_econ", "ctd_bowl_sr",
    "ctd_bowl_4w_count", "ctd_bowl_5w_count",
]


# ─────────────────────────────────────────────────────────────────────────────

def _num(val, default=None):
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _debut_age(dob_str, match_date_str):
    try:
        dob   = datetime.strptime(str(dob_str)[:10],        "%Y-%m-%d")
        debut = datetime.strptime(str(match_date_str)[:10], "%Y-%m-%d")
        years  = debut.year  - dob.year
        months = debut.month - dob.month
        if months < 0:
            years  -= 1
            months += 12
        return f"{years}y {months}m"
    except (ValueError, TypeError):
        return None


def pull_deliveries(since_date):
    conn, cursor = set_conn_cursor()
    print("  Executing query (may take 30–60 s)…")
    rows = run_query(build_query(since_date), conn, cursor)
    conn.close()
    return rows


def prepare(rows):
    result = []
    for r in rows:
        r = dict(r)

        for col in ("bat_score", "wide_runs", "noball_runs", "bye_runs", "legbye_runs",
                    "striker_id", "bowler_id", "batter_out_id",
                    "striker_batting_position", "bowler_bowling_position"):
            r[col] = _num(r.get(col))

        lb = str(r.get("legal_ball", "")).strip().lower()
        r["is_legal"] = lb in ("1", "true")

        r["batter_out"] = (
            r["batter_out_id"] is not None and r["batter_out_id"] == r["striker_id"]
        )

        bd = str(r.get("bowler_dismissal", "")).strip().lower()
        r["bowler_wkt"] = bd in ("true", "1")

        result.append(r)
    return result


def match_meta(rows):
    seen = {}
    for r in rows:
        mid = r["match_id"]
        if mid not in seen:
            seen[mid] = {
                "match_id": mid,
                "match_date": r["match_date"],
                "opponent": r["opponent"],
                "venue": r["venue"],
                "series": r["series"],
            }
    return seen


def compute_batting(rows):
    groups = defaultdict(list)
    for r in rows:
        groups[(r["match_id"], r["striker_id"])].append(r)

    result = []
    for (match_id, striker_id), grp in groups.items():
        legal = [r for r in grp if r["is_legal"]]
        runs  = int(sum(r["bat_score"] or 0 for r in legal))
        balls = len(legal)
        fours = sum(1 for r in legal if r["bat_score"] == 4)
        sixes = sum(1 for r in legal if r["bat_score"] == 6)

        dismissed = [r for r in grp if r["batter_out"]]
        not_out   = not dismissed
        how_out   = dismissed[0]["how_out"].strip() if dismissed else "Not Out"

        positions = [r["striker_batting_position"] for r in grp if r["striker_batting_position"] is not None]
        pos = int(min(positions)) if positions else None

        dob = next((r["striker_dob"] for r in grp
                    if r.get("striker_dob") not in (None, "None", "")), None)
        result.append({
            "match_id":    match_id,
            "player_id":   str(int(striker_id)),
            "player_name": grp[0]["striker_name"].strip(),
            "dob":         dob,
            "bat_pos":     pos,
            "bat_runs":    runs,
            "bat_balls":   balls,
            "bat_fours":   fours,
            "bat_sixes":   sixes,
            "bat_sr":      round(runs / balls * 100, 2) if balls > 0 else None,
            "bat_not_out": int(not_out),
            "bat_how_out": how_out,
            "bat_50":      int(50 <= runs < 100),
            "bat_100":     int(runs >= 100),
        })
    return result


def compute_bowling(rows):
    groups = defaultdict(list)
    for r in rows:
        groups[(r["match_id"], r["bowler_id"])].append(r)

    result = []
    for (match_id, bowler_id), grp in groups.items():
        legal   = [r for r in grp if r["is_legal"]]
        n_balls = len(legal)
        runs    = int(
            sum(r["bat_score"]   or 0 for r in grp)
            + sum(r["wide_runs"]   or 0 for r in grp)
            + sum(r["noball_runs"] or 0 for r in grp)
        )
        wkts = sum(1 for r in grp if r["bowler_wkt"])
        dots = sum(1 for r in legal if (r["bat_score"] or 0) == 0)

        positions = [r["bowler_bowling_position"] for r in grp if r["bowler_bowling_position"] is not None]
        pos = int(min(positions)) if positions else None

        dob = next((r["bowler_dob"] for r in grp
                    if r.get("bowler_dob") not in (None, "None", "")), None)
        result.append({
            "match_id":     match_id,
            "player_id":    str(int(bowler_id)),
            "player_name":  grp[0]["bowler_name"].strip(),
            "dob":          dob,
            "bowl_pos":     pos,
            "bowl_balls":   n_balls,
            "bowl_overs":   f"{n_balls // 6}.{n_balls % 6}",
            "bowl_runs":    runs,
            "bowl_wkts":    wkts,
            "bowl_econ":    round(runs / (n_balls / 6), 2) if n_balls > 0 else None,
            "bowl_dot_pct": round(dots / n_balls * 100, 1) if n_balls > 0 else None,
            "bowl_4w":      int(wkts >= 4),
            "bowl_5w":      int(wkts >= 5),
        })
    return result


def compute_match_results(rows):
    by_match = defaultdict(list)
    for r in rows:
        by_match[r["match_id"]].append(r)

    results = {}
    for match_id, mrows in by_match.items():
        row = {"match_id": match_id, "aus_result": "no_result",
               "aus_bat_innings": None, "aus_runs": None, "aus_wkts": None,
               "opp_runs": None, "opp_wkts": None}

        scores = {}
        for inn in ("1", "2"):
            irows = [r for r in mrows if r["match_innings"] == inn]
            if not irows:
                continue
            runs = int(
                sum(r["bat_score"]   or 0 for r in irows)
                + sum(r["wide_runs"]   or 0 for r in irows)
                + sum(r["noball_runs"] or 0 for r in irows)
                + sum(r["bye_runs"]    or 0 for r in irows)
                + sum(r["legbye_runs"] or 0 for r in irows)
            )
            wkts     = sum(1 for r in irows if r["batter_out"])
            team_bat = irows[0]["team_batting_id"]
            scores[inn] = {"runs": runs, "wkts": wkts, "team_bat": team_bat}

        if "1" not in scores or "2" not in scores:
            results[match_id] = row
            continue

        s1, s2       = scores["1"], scores["2"]
        aus_bat_inn  = "1" if s1["team_bat"] == AUS_TEAM_ID else "2"
        aus_s, opp_s = (s1, s2) if aus_bat_inn == "1" else (s2, s1)

        if s2["runs"] > s1["runs"]:
            winner = s2["team_bat"]
        elif s1["runs"] > s2["runs"]:
            winner = s1["team_bat"]
        elif s1["runs"] == s2["runs"] and s2["wkts"] >= 10:
            winner = "tied"
        else:
            winner = "no_result"

        aus_result = (
            "tied"      if winner == "tied"       else
            "no_result" if winner == "no_result"  else
            "won"       if winner == AUS_TEAM_ID  else
            "lost"
        )
        row.update({
            "aus_result":      aus_result,
            "aus_bat_innings": int(aus_bat_inn),
            "aus_runs":        aus_s["runs"],
            "aus_wkts":        aus_s["wkts"],
            "opp_runs":        opp_s["runs"],
            "opp_wkts":        opp_s["wkts"],
        })
        results[match_id] = row
    return results


def merge_bat_bowl(bat_rows, bowl_rows):
    combined = {}

    for row in bat_rows:
        key = (row["match_id"], row["player_id"])
        combined[key] = dict(row)

    for row in bowl_rows:
        key = (row["match_id"], row["player_id"])
        bowl_fields = {k: v for k, v in row.items() if k.startswith("bowl_")}
        if key in combined:
            combined[key].update(bowl_fields)
            if not combined[key].get("dob") and row.get("dob"):
                combined[key]["dob"] = row["dob"]
        else:
            combined[key] = dict(row)

    return list(combined.values())


def add_career_to_date(player_matches):
    by_player = defaultdict(list)
    for row in player_matches:
        by_player[row["player_id"]].append(row)

    result = []
    for matches in by_player.values():
        matches.sort(key=lambda x: x["match_date"])

        debut_date = matches[0].get("match_date", "") if matches else ""
        dob        = matches[0].get("dob") if matches else None
        debut_age  = _debut_age(dob, debut_date) if matches else None
        age_at_10  = _debut_age(dob, matches[9]["match_date"])  if len(matches) >= 10 else None
        age_at_20  = _debut_age(dob, matches[19]["match_date"]) if len(matches) >= 20 else None

        ctd = dict(
            bat_innings=0, bat_not_outs=0, bat_runs=0, bat_balls=0,
            bat_50s=0, bat_100s=0, bat_hs=0,
            bowl_innings=0, bowl_wkts=0, bowl_runs=0, bowl_balls=0,
            bowl_4w_count=0, bowl_5w_count=0,
        )

        for num, match in enumerate(matches, 1):
            match["career_match_num"] = num
            match["debut_date"]       = debut_date
            match["debut_age"]        = debut_age
            match["age_at_10"]        = age_at_10
            match["age_at_20"]        = age_at_20

            # Accumulate this match first, then record — so ctd_ = stats *through* this match
            if match.get("bat_runs") is not None:
                ctd["bat_innings"]   += 1
                ctd["bat_not_outs"]  += match.get("bat_not_out", 0)
                ctd["bat_runs"]      += match.get("bat_runs", 0)
                ctd["bat_balls"]     += match.get("bat_balls", 0)
                ctd["bat_50s"]       += match.get("bat_50", 0)
                ctd["bat_100s"]      += match.get("bat_100", 0)
                ctd["bat_hs"]         = max(ctd["bat_hs"], match.get("bat_runs", 0))

            if match.get("bowl_balls") is not None:
                ctd["bowl_innings"]  += 1
                ctd["bowl_wkts"]     += match.get("bowl_wkts", 0)
                ctd["bowl_runs"]     += match.get("bowl_runs", 0)
                ctd["bowl_balls"]    += match.get("bowl_balls", 0)
                ctd["bowl_4w_count"] += match.get("bowl_4w", 0)
                ctd["bowl_5w_count"] += match.get("bowl_5w", 0)

            match["ctd_bat_innings"]   = ctd["bat_innings"]
            match["ctd_bat_not_outs"]  = ctd["bat_not_outs"]
            match["ctd_bat_runs"]      = ctd["bat_runs"]
            match["ctd_bat_balls"]     = ctd["bat_balls"]
            match["ctd_bat_50s"]       = ctd["bat_50s"]
            match["ctd_bat_100s"]      = ctd["bat_100s"]
            match["ctd_bat_hs"]        = ctd["bat_hs"]
            match["ctd_bowl_innings"]  = ctd["bowl_innings"]
            match["ctd_bowl_wkts"]     = ctd["bowl_wkts"]
            match["ctd_bowl_runs"]     = ctd["bowl_runs"]
            match["ctd_bowl_balls"]    = ctd["bowl_balls"]
            match["ctd_bowl_4w_count"] = ctd["bowl_4w_count"]
            match["ctd_bowl_5w_count"] = ctd["bowl_5w_count"]

            denom = ctd["bat_innings"] - ctd["bat_not_outs"]
            match["ctd_bat_avg"] = round(ctd["bat_runs"] / denom, 2) if denom > 0 else None
            match["ctd_bat_bpd"] = round(ctd["bat_balls"] / denom, 1) if denom > 0 else None
            match["ctd_bat_sr"]  = (
                round(ctd["bat_runs"] / ctd["bat_balls"] * 100, 2)
                if ctd["bat_balls"] > 0 else None
            )
            match["ctd_bowl_avg"]  = (
                round(ctd["bowl_runs"] / ctd["bowl_wkts"], 2)
                if ctd["bowl_wkts"] > 0 else None
            )
            match["ctd_bowl_econ"] = (
                round(ctd["bowl_runs"] / (ctd["bowl_balls"] / 6), 2)
                if ctd["bowl_balls"] > 0 else None
            )
            match["ctd_bowl_sr"] = (
                round(ctd["bowl_balls"] / ctd["bowl_wkts"], 2)
                if ctd["bowl_wkts"] > 0 else None
            )

            result.append(match)

    return result


def main(out_path, since_date):
    print(f"Pulling deliveries from database (since {since_date})…")
    raw = pull_deliveries(since_date)
    n_matches = len({r["match_id"] for r in raw})
    print(f"  → {len(raw):,} deliveries across {n_matches} matches")

    rows = prepare(raw)

    meta    = match_meta(rows)
    results = compute_match_results(rows)

    print("Computing batting stats…")
    bat_rows = compute_batting([r for r in rows if r["team_batting_id"] == AUS_TEAM_ID])
    print(f"  → {len(bat_rows):,} batter-match rows")

    print("Computing bowling stats…")
    bowl_rows = compute_bowling([r for r in rows if r["team_bowling_id"] == AUS_TEAM_ID])
    print(f"  → {len(bowl_rows):,} bowler-match rows")

    print("Merging batting + bowling…")
    merged = merge_bat_bowl(bat_rows, bowl_rows)
    for row in merged:
        mid = row["match_id"]
        if mid in meta:
            row.update(meta[mid])
        if mid in results:
            row.update({k: v for k, v in results[mid].items() if k != "match_id"})

    print("Adding career-to-date stats…")
    final = add_career_to_date(merged)
    final.sort(key=lambda x: (x["player_id"], x["career_match_num"]))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COL_ORDER, extrasaction="ignore", restval="")
        writer.writeheader()
        writer.writerows(final)

    n_players = len({r["player_id"] for r in final})
    print(f"\nSaved {len(final):,} rows ({n_players} players) → {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUTPUT_DEFAULT,
                        help="Output CSV path")
    parser.add_argument("--since", default=ODI_CUTOFF_DATE, metavar="YYYY-MM-DD",
                        help=f"Pull matches after this date (default: {ODI_CUTOFF_DATE})")
    args = parser.parse_args()
    main(args.out, args.since)
