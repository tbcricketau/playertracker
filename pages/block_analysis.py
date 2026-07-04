import plotly.graph_objects as go
import streamlit as st

from data import load_data, get_all_players, get_opponents, show_debut_table

BLOCK_METRICS = {
    "Bowling average":     "bowl_avg",
    "Economy rate":        "bowl_econ",
    "Bowling strike rate": "bowl_sr",
}
METRIC_LABELS = list(BLOCK_METRICS.keys())
DEFAULTS = ["Bowling average", "Economy rate", "Bowling strike rate"]

BLOCK_COLORS = ["#636EFA", "#EF553B", "#00CC96"]


def compute_block(rows, player, b_start, b_end):
    """Aggregate bowling stats for a player within a career match number range."""
    player_rows = [
        r for r in rows
        if r["player_name"] == player
        and r.get("career_match_num") is not None
        and r["career_match_num"] >= b_start
        and (b_end is None or r["career_match_num"] <= b_end)
        and r.get("bowl_balls") is not None
        and r["bowl_balls"] > 0
    ]
    if not player_rows:
        return None

    balls = sum(r["bowl_balls"] or 0 for r in player_rows)
    runs  = sum(r["bowl_runs"]  or 0 for r in player_rows)
    wkts  = sum(r["bowl_wkts"]  or 0 for r in player_rows)
    games = len(player_rows)

    return {
        "bowl_avg":  round(runs / wkts, 2)        if wkts > 0  else None,
        "bowl_sr":   round(balls / wkts, 2)       if wkts > 0  else None,
        "bowl_econ": round(runs / (balls / 6), 2) if balls > 0 else None,
        "wkts":      int(wkts),
        "games":     games,
    }


def make_block_chart(block_data, selected_players, blocks, metric_key, metric_label):
    fig = go.Figure()
    for (label, _, _), color in zip(blocks, BLOCK_COLORS):
        y     = []
        wkts  = []
        games = []
        for p in selected_players:
            stats = block_data[p].get(label)
            y.append(stats.get(metric_key) if stats else None)
            wkts.append(stats["wkts"]  if stats else 0)
            games.append(stats["games"] if stats else 0)

        fig.add_trace(go.Bar(
            name=label,
            x=selected_players,
            y=y,
            marker_color=color,
            customdata=list(zip(wkts, games)),
            hovertemplate=(
                "<b>%{x}</b><br>"
                f"{metric_label}: %{{y:.2f}}<br>"
                "Wickets: %{customdata[0]}<br>"
                "Games bowled: %{customdata[1]}"
                "<extra></extra>"
            ),
        ))

    fig.update_layout(
        barmode="group",
        title=dict(text=metric_label, x=0.5, xanchor="center"),
        height=400,
        margin=dict(t=45, b=20, l=50, r=10),
        showlegend=False,
    )
    return fig


rows = load_data()

if not rows:
    st.error(
        "No data found. Run the ETL script first:\n\n"
        "`.venv\\Scripts\\activate` then `python scripts/build_player_career.py`"
    )
    st.stop()

st.title("Block Analysis — Bowling")

all_players   = get_all_players(rows)
all_opponents = get_opponents(rows)

# Session state defaults
if "selected_players" not in st.session_state:
    st.session_state["selected_players"] = []
if "selected_opponents" not in st.session_state:
    st.session_state["selected_opponents"] = []
if "block_metric_labels" not in st.session_state:
    st.session_state["block_metric_labels"] = list(DEFAULTS)

with st.sidebar:
    st.header("Controls")
    selected_players = st.multiselect(
        "Players",
        all_players,
        key="selected_players",
    )

    st.divider()
    st.subheader("Match filter")
    selected_opponents = st.multiselect(
        "Opponent",
        all_opponents,
        key="selected_opponents",
    )

    st.divider()
    st.subheader("Block boundaries")
    b1_end = st.slider("End of block 1", min_value=1, max_value=49, value=10)
    b2_end = st.slider("End of block 2", min_value=b1_end + 1, max_value=100, value=max(b1_end + 1, 20))

    st.divider()
    st.subheader("Metrics")
    current = st.session_state["block_metric_labels"]
    def _idx(val):
        try:
            return METRIC_LABELS.index(val)
        except ValueError:
            return 0

    m0 = st.selectbox("Chart 1", METRIC_LABELS, index=_idx(current[0]))
    m1 = st.selectbox("Chart 2", METRIC_LABELS, index=_idx(current[1]))
    m2 = st.selectbox("Chart 3", METRIC_LABELS, index=_idx(current[2]))
    metric_labels = [m0, m1, m2]
    st.session_state["block_metric_labels"] = metric_labels

if not selected_players:
    st.info("Select one or more players from the sidebar to get started.")
    st.stop()

blocks = [
    (f"Matches 1–{b1_end}",          1,            int(b1_end)),
    (f"Matches {b1_end+1}–{b2_end}", int(b1_end)+1, int(b2_end)),
    (f"Matches {b2_end+1}+",         int(b2_end)+1, None),
]

opp_set = set(selected_opponents)
filtered_rows = [r for r in rows if not opp_set or r.get("opponent") in opp_set]

# Compute block stats for all selected players
block_data = {
    player: {label: compute_block(filtered_rows, player, start, end) for label, start, end in blocks}
    for player in selected_players
}

# Shared legend above all three charts
legend_html = "&nbsp;&nbsp;&nbsp;".join(
    f'<span style="color:{color}; font-size:20px;">&#9632;</span>&nbsp;{label}'
    for (label, _, _), color in zip(blocks, BLOCK_COLORS)
)
st.markdown(
    f"<div style='text-align:center; margin-bottom:4px;'>{legend_html}</div>",
    unsafe_allow_html=True,
)

cols = st.columns(3)
for col, label in zip(cols, metric_labels):
    fig = make_block_chart(
        block_data, selected_players, blocks,
        BLOCK_METRICS[label], label,
    )
    col.plotly_chart(fig, use_container_width=True)

show_debut_table(rows, selected_players)
