import streamlit as st

st.set_page_config(page_title="AUS ODI Career Tracker", layout="wide")

pg = st.navigation([
    st.Page("pages/career_progression.py", title="Career Progression", icon="📈"),
    st.Page("pages/block_analysis.py",     title="Block Analysis",     icon="📊"),
])
pg.run()
