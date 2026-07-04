import plotly.graph_objects as go
import streamlit as st

from data import load_data, get_all_players, get_opponents, show_debut_table

METRICS = {
    "Batting average":     "ctd_bat_avg",
    "Batting strike rate": "ctd_bat_sr",
    "Balls per dismissal": "ctd_bat_bpd",
    "Career runs":         "ctd_bat_runs",
    "Bowling average":     "ctd_bowl_avg",
    "Economy rate":        "ctd_bowl_econ",
    "Bowling strike rate": "ctd_bowl_sr",
    "Career wickets":      "ctd_bowl_wkts",
}
METRIC_LABELS = list(METRICS.keys())

DEFAULTS = {
    "Batting": ["Batting average", "Batting strike rate", "Balls per dismissal"],
    "Bowling": ["Bowling average", "Economy rate", "Bowling strike rate"],
}


def make_chart(filtered, selected_players, metric_col, metric_label, max_games):
    fig = go.Figure()
    for player in selected_players:
        player_rows = sorted(
            [r for r in filtered if r["player_name"] == player],
            key=lambda r: r["career_match_num"],
        )
        x = [r["career_match_num"] for r in player_rows]
        y = [r[metric_col] for r in player_rows]
        if all(v is None for v in y):
            continue
        fig.add_trace(go.Scatter(
            x=x, y=y,
            name=player,
            mode="lines+markers",
            connectgaps=False,
        ))
    fig.update_layout(
        title=dict(text=metric_label, x=0.5, xanchor="center"),
        hovermode="x unified",
        height=370,
        margin=dict(t=45, b=20, l=50, r=10),
        showlegend=False,
        xaxis=dict(range=[1, max_games], title=None),
    )
    return fig


def on_preset_change():
    preset = st.session_state["metric_preset"]
    st.session_state["metric_labels"] = list(DEFAULTS[preset])


rows = load_data()

if not rows:
    st.error(
        "No data found. Run the ETL script first:\n\n"
        "`.venv\\Scripts\\activate` then `python scripts/build_player_career.py`"
    )
    st.stop()

st.title("Career Progression")

all_players  = get_all_players(rows)
all_opponents = get_opponents(rows)

# Session state defaults
if "selected_players" not in st.session_state:
    st.session_state["selected_players"] = []
if "selected_opponents" not in st.session_state:
    st.session_state["selected_opponents"] = []
if "metric_preset" not in st.session_state:
    st.session_state["metric_preset"] = "Bowling"
if "metric_labels" not in st.session_state:
    st.session_state["metric_labels"] = list(DEFAULTS["Bowling"])

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

    max_games = st.slider("Career matches (x-axis)", min_value=5, max_value=100, value=20)

    st.divider()
    st.subheader("Metrics")
    st.radio(
        "Quick select",
        ["Batting", "Bowling"],
        horizontal=True,
        key="metric_preset",
        on_change=on_preset_change,
    )

    current = st.session_state["metric_labels"]
    def _idx(val):
        try:
            return METRIC_LABELS.index(val)
        except ValueError:
            return 0

    m0 = st.selectbox("Chart 1", METRIC_LABELS, index=_idx(current[0]))
    m1 = st.selectbox("Chart 2", METRIC_LABELS, index=_idx(current[1]))
    m2 = st.selectbox("Chart 3", METRIC_LABELS, index=_idx(current[2]))
    metric_labels = [m0, m1, m2]
    st.session_state["metric_labels"] = metric_labels

if not selected_players:
    st.info("Select one or more players from the sidebar to get started.")
    st.stop()

opp_set = set(selected_opponents)
filtered = [
    r for r in rows
    if r["player_name"] in selected_players
    and r["career_match_num"] is not None
    and 1 <= r["career_match_num"] <= max_games
    and (not opp_set or r.get("opponent") in opp_set)
]

cols = st.columns(3)
for col, label in zip(cols, metric_labels):
    fig = make_chart(filtered, selected_players, METRICS[label], label, max_games)
    col.plotly_chart(fig, use_container_width=True)

st.markdown(
    "<div style='text-align:center; color:gray; font-size:13px; margin-top:-24px;'>"
    "Career match</div>",
    unsafe_allow_html=True,
)

show_debut_table(rows, selected_players)
