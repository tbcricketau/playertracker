"""PILOT: build ODI career progression from scorecarddb — any nation, not just Australia.

The warehouse is CA-centric ball-by-ball, so build_player_career.py can only track Australians.
scorecarddb holds every nation's ODI scorecards resolved to warehouse ids, so this produces the
same career-progression CSV for any international player — the capability the warehouse can't give.

Sources: scorecarddb store (per-match batting/bowling cards + match context) for the figures and
career-to-date accumulation; the warehouse Players table (via the resolved id) for DOB/age. A few
ball-derived columns the scorecard lacks (dot %, exact bowling position) are left blank — that is the
scorecard-level boundary.

    python scripts/build_career_from_scorecard.py            # -> data/odi_career_scorecard.csv
    set PLAYERTRACKER_CSV=...\\data\\odi_career_scorecard.csv & streamlit run app.py
"""

import argparse
import csv
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from config import DATA_SCHEMA
from cricket_core.warehouse import run_query, set_conn_cursor

STORE = Path(__file__).resolve().parent.parent.parent / "scorecarddb" / "data" / "scorecarddb.sqlite"
OUT_DEFAULT = Path(__file__).resolve().parent.parent / "data" / "odi_career_scorecard.csv"
ODI = "One-day internationals"

COL_ORDER = [
    "player_id", "player_name", "career_match_num", "debut_date", "debut_age", "age_at_10", "age_at_20",
    "match_id", "match_date", "opponent", "venue", "series",
    "bat_pos", "bat_runs", "bat_balls", "bat_fours", "bat_sixes", "bat_sr", "bat_not_out", "bat_how_out",
    "ctd_bat_innings", "ctd_bat_not_outs", "ctd_bat_runs", "ctd_bat_balls",
    "ctd_bat_avg", "ctd_bat_sr", "ctd_bat_bpd", "ctd_bat_50s", "ctd_bat_100s", "ctd_bat_hs",
    "bowl_pos", "bowl_overs", "bowl_balls", "bowl_runs", "bowl_wkts", "bowl_econ", "bowl_4w", "bowl_5w",
    "ctd_bowl_innings", "ctd_bowl_wkts", "ctd_bowl_runs", "ctd_bowl_balls",
    "ctd_bowl_avg", "ctd_bowl_econ", "ctd_bowl_sr", "ctd_bowl_4w_count", "ctd_bowl_5w_count",
]


def _age(dob, when):
    try:
        d = datetime.strptime(str(dob)[:10], "%Y-%m-%d")
        w = datetime.strptime(str(when)[:10], "%Y-%m-%d")
        yrs, mos = w.year - d.year, w.month - d.month
        if mos < 0:
            yrs, mos = yrs - 1, mos + 12
        return f"{yrs}y {mos}m"
    except (ValueError, TypeError):
        return None


def load_store() -> dict:
    """Merge scorecarddb ODI cards + context into {(wh_player, match): row}."""
    c = sqlite3.connect(f"file:{STORE}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    match = {r["source_match_id"]: r for r in c.execute(
        f"SELECT source_match_id, start_date, team1_id, team1_name, team2_id, team2_name, ground "
        f"FROM matches WHERE class_name='{ODI}'")}
    team = {(r["source_match_id"], r["wh_player_id"]): r["team_id"] for r in c.execute(
        f"SELECT a.source_match_id, a.wh_player_id, a.team_id FROM appearances a "
        f"JOIN matches m ON m.source_match_id=a.source_match_id "
        f"WHERE m.class_name='{ODI}' AND a.wh_player_id IS NOT NULL")}

    rows: dict = {}

    def opp(mid, pid):
        m = match.get(mid)
        if not m:
            return ""
        tid = team.get((mid, pid))
        return m["team2_name"] if str(tid) == str(m["team1_id"]) else m["team1_name"]

    for b in c.execute(f"SELECT b.wh_player_id p, b.source_match_id mid, b.batting_position pos, "
                       f"b.runs, b.balls, b.fours, b.sixes, b.is_out, b.dismissal_str "
                       f"FROM batting_cards b JOIN matches m ON m.source_match_id=b.source_match_id "
                       f"WHERE m.class_name='{ODI}' AND b.wh_player_id IS NOT NULL"):
        m = match[b["mid"]]
        runs, balls = b["runs"] or 0, b["balls"] or 0
        rows[(b["p"], b["mid"])] = {
            "player_id": b["p"], "match_id": b["mid"], "match_date": str(m["start_date"])[:10],
            "opponent": opp(b["mid"], b["p"]), "venue": m["ground"] or "", "series": "",
            "bat_pos": b["pos"], "bat_runs": runs, "bat_balls": balls,
            "bat_fours": b["fours"] or 0, "bat_sixes": b["sixes"] or 0,
            "bat_sr": round(runs / balls * 100, 2) if balls else None,
            "bat_not_out": 0 if b["is_out"] == 1 else 1,
            "bat_how_out": "Not Out" if b["is_out"] != 1 else (b["dismissal_str"] or "out"),
            "bat_50": int(50 <= runs < 100), "bat_100": int(runs >= 100),
        }
    for w in c.execute(f"SELECT w.wh_player_id p, w.source_match_id mid, w.balls, w.conceded, "
                       f"w.wickets, w.economy FROM bowling_cards w "
                       f"JOIN matches m ON m.source_match_id=w.source_match_id "
                       f"WHERE m.class_name='{ODI}' AND w.wh_player_id IS NOT NULL"):
        wk, bl, rc = w["wickets"] or 0, w["balls"] or 0, w["conceded"] or 0
        base = rows.get((w["p"], w["mid"]))
        if base is None:
            m = match[w["mid"]]
            base = rows[(w["p"], w["mid"])] = {
                "player_id": w["p"], "match_id": w["mid"], "match_date": str(m["start_date"])[:10],
                "opponent": opp(w["mid"], w["p"]), "venue": m["ground"] or "", "series": ""}
        base.update({
            "bowl_pos": None, "bowl_balls": bl, "bowl_overs": f"{bl // 6}.{bl % 6}",
            "bowl_runs": rc, "bowl_wkts": wk,
            "bowl_econ": round(rc / (bl / 6), 2) if bl else None,
            "bowl_4w": int(wk >= 4), "bowl_5w": int(wk >= 5),
        })
    c.close()
    return rows


def names_and_dobs(rows: list, conn, cur) -> dict:
    """Stamp player_name from the warehouse; return {player_id: dob}."""
    pids = sorted({r["player_id"] for r in rows})
    name_of, dob_of = {}, {}
    for i in range(0, len(pids), 900):
        batch = ",".join(pids[i:i + 900])
        for r in run_query(f"SELECT player_id, name, surname, CAST(date_of_birth AS DATE) dob "
                           f"FROM [{DATA_SCHEMA}].[Players] WHERE player_id IN ({batch})", conn, cur) or []:
            pid = str(r["player_id"])
            name_of[pid] = f"{(r.get('name') or '').strip()} {(r.get('surname') or '').strip()}".strip()
            dob_of[pid] = r.get("dob")
    for r in rows:
        r["player_name"] = name_of.get(r["player_id"]) or r["player_id"]
    return dob_of


def career_to_date(rows: list, dob_of: dict) -> list:
    by_player = defaultdict(list)
    for r in rows:
        by_player[r["player_id"]].append(r)
    out = []
    for matches in by_player.values():
        matches.sort(key=lambda x: x["match_date"])
        dob = dob_of.get(matches[0]["player_id"])
        debut = matches[0]["match_date"]
        c = dict(bi=0, bno=0, br=0, bb=0, b50=0, b100=0, bhs=0, wi=0, ww=0, wr=0, wb=0, w4=0, w5=0)
        for n, m in enumerate(matches, 1):
            m["career_match_num"] = n
            m["debut_date"] = debut
            m["debut_age"] = _age(dob, debut)
            m["age_at_10"] = _age(dob, matches[9]["match_date"]) if len(matches) >= 10 else None
            m["age_at_20"] = _age(dob, matches[19]["match_date"]) if len(matches) >= 20 else None
            if m.get("bat_runs") is not None:
                c["bi"] += 1; c["bno"] += m.get("bat_not_out", 0); c["br"] += m["bat_runs"]
                c["bb"] += m.get("bat_balls", 0); c["b50"] += m.get("bat_50", 0)
                c["b100"] += m.get("bat_100", 0); c["bhs"] = max(c["bhs"], m["bat_runs"])
            if m.get("bowl_balls") is not None:
                c["wi"] += 1; c["ww"] += m.get("bowl_wkts", 0); c["wr"] += m.get("bowl_runs", 0)
                c["wb"] += m.get("bowl_balls", 0); c["w4"] += m.get("bowl_4w", 0); c["w5"] += m.get("bowl_5w", 0)
            outs = c["bi"] - c["bno"]
            m.update({
                "ctd_bat_innings": c["bi"], "ctd_bat_not_outs": c["bno"], "ctd_bat_runs": c["br"],
                "ctd_bat_balls": c["bb"], "ctd_bat_50s": c["b50"], "ctd_bat_100s": c["b100"], "ctd_bat_hs": c["bhs"],
                "ctd_bat_avg": round(c["br"] / outs, 2) if outs else None,
                "ctd_bat_bpd": round(c["bb"] / outs, 1) if outs else None,
                "ctd_bat_sr": round(c["br"] / c["bb"] * 100, 2) if c["bb"] else None,
                "ctd_bowl_innings": c["wi"], "ctd_bowl_wkts": c["ww"], "ctd_bowl_runs": c["wr"],
                "ctd_bowl_balls": c["wb"], "ctd_bowl_4w_count": c["w4"], "ctd_bowl_5w_count": c["w5"],
                "ctd_bowl_avg": round(c["wr"] / c["ww"], 2) if c["ww"] else None,
                "ctd_bowl_econ": round(c["wr"] / (c["wb"] / 6), 2) if c["wb"] else None,
                "ctd_bowl_sr": round(c["wb"] / c["ww"], 2) if c["ww"] else None,
            })
            out.append(m)
    return out


def main(out_path: Path) -> int:
    if not STORE.exists():
        sys.exit(f"scorecarddb store not found at {STORE}")
    print("Loading scorecarddb ODI cards ...")
    merged = list(load_store().values())
    print(f"  {len(merged):,} player-match rows across {len({r['match_id'] for r in merged}):,} ODIs")

    conn, cur = set_conn_cursor()
    dob_of = names_and_dobs(merged, conn, cur)
    final = career_to_date(merged, dob_of)
    final.sort(key=lambda x: (x["player_name"], x["career_match_num"]))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COL_ORDER, extrasaction="ignore", restval="")
        w.writeheader()
        w.writerows(final)
    print(f"Saved {len(final):,} rows ({len({r['player_name'] for r in final}):,} players) -> {out_path}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT_DEFAULT)
    raise SystemExit(main(ap.parse_args().out))
