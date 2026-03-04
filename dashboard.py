"""
dashboard.py — Interactive Project Dashboard
Built with Streamlit

Run with:
    streamlit run dashboard.py
"""

import pandas as pd
import streamlit as st
import plotly.express as px
from pathlib import Path

st.set_page_config(
    page_title="DataTaxonomy Dashboard",
    page_icon="📊",
    layout="wide",
)

st.markdown("""
<style>
    [data-testid="metric-container"] {
        background: #f8f9fb; border: 1px solid #e2e6ea;
        border-radius: 10px; padding: 12px 16px;
    }
    .section-label {
        font-size: 11px; font-weight: 700; letter-spacing: 1.2px;
        text-transform: uppercase; color: #718096; margin-bottom: 6px;
    }
</style>
""", unsafe_allow_html=True)

# Load config
from config_loader import load_config, get_paths_config, get_project_config

try:
    config = load_config("config.yaml")
    paths = get_paths_config(config)
    project = get_project_config(config)
    CSV_PATH = paths["output_csv"]
except Exception as e:
    st.error(f"❌ Configuration error: {e}")
    st.stop()

@st.cache_data
def load_data(path):
    df = pd.read_csv(path)
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    return df

if not Path(CSV_PATH).exists():
    st.error(f"❌ Could not find {CSV_PATH}. Run 'python main.py' first.")
    st.stop()

df = load_data(CSV_PATH)

# ── Header ────────────────────────────────────────────────────────────
st.title("📊 DataTaxonomy Dashboard")
st.caption(f"Project: **{project['name']}** ({project['location']})")
st.caption(f"Source: {CSV_PATH} · {len(df)} files processed")
st.divider()

# ── Sidebar Filters ───────────────────────────────────────────────────
st.sidebar.header("🔍 Filters")
all_domains    = sorted(df["domain"].dropna().unique())
all_scales     = sorted(df["scale"].dropna().unique())
all_lifecycles = sorted(df["lifecycle"].dropna().unique())
all_priorities = sorted(df["review_priority"].dropna().unique())

sel_domains    = st.sidebar.multiselect("Domain",     all_domains,    default=all_domains)
sel_scales     = st.sidebar.multiselect("Scale",      all_scales,     default=all_scales)
sel_lifecycles = st.sidebar.multiselect("Lifecycle",  all_lifecycles, default=all_lifecycles)
sel_priorities = st.sidebar.multiselect("Review Priority", all_priorities, default=all_priorities)

filtered = df[
    df["domain"].isin(sel_domains) &
    df["scale"].isin(sel_scales) &
    df["lifecycle"].isin(sel_lifecycles) &
    df["review_priority"].isin(sel_priorities)
]
st.sidebar.caption(f"**{len(filtered)}** of {len(df)} files shown")

# ── Key Metrics ───────────────────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Files", len(filtered))
col2.metric("Urgent Review", int((filtered["review_priority"] == "Urgent").sum()))
col3.metric("Confidential", int((filtered["confidentiality"] == "Confidential").sum()))
col4.metric("Data Assets", int((filtered["asset_type"] == "Data").sum()))

st.divider()

# ── Tabs ──────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["Overview", "By Domain", "By Priority", "Data"])

with tab1:
    st.markdown('<div class="section-label">Review Priority Distribution</div>', unsafe_allow_html=True)
    priority_counts = filtered["review_priority"].value_counts()
    if not priority_counts.empty:
        fig = px.pie(values=priority_counts.values, names=priority_counts.index,
                     color_discrete_sequence=["#ef553b", "#ff9500", "#ffd700", "#00cc96"])
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data available")

    st.markdown('<div class="section-label">Asset Type Distribution</div>', unsafe_allow_html=True)
    asset_counts = filtered["asset_type"].value_counts()
    if not asset_counts.empty:
        fig = px.bar(x=asset_counts.index, y=asset_counts.values, labels={"x": "Asset Type", "y": "Count"})
        st.plotly_chart(fig, use_container_width=True)

with tab2:
    st.markdown('<div class="section-label">Files by Domain</div>', unsafe_allow_html=True)
    domain_counts = filtered["domain"].value_counts()
    if not domain_counts.empty:
        fig = px.bar(x=domain_counts.index, y=domain_counts.values, labels={"x": "Domain", "y": "Count"})
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No data available")

    st.markdown('<div class="section-label">Lifecycle Distribution</div>', unsafe_allow_html=True)
    lifecycle_counts = filtered["lifecycle"].value_counts()
    if not lifecycle_counts.empty:
        fig = px.bar(x=lifecycle_counts.index, y=lifecycle_counts.values, labels={"x": "Lifecycle", "y": "Count"})
        st.plotly_chart(fig, use_container_width=True)

with tab3:
    st.markdown('<div class="section-label">Files Needing Review</div>', unsafe_allow_html=True)
    urgent = filtered[filtered["review_priority"] == "Urgent"]
    if len(urgent) > 0:
        st.dataframe(urgent[["filename", "domain", "confidentiality", "action"]].head(20), use_container_width=True)
    else:
        st.success("✅ No urgent reviews needed!")

    st.markdown('<div class="section-label">Review Reasons Summary</div>', unsafe_allow_html=True)
    reasons = filtered["review_reasons"].str.split(", ").explode().value_counts().head(10)
    if not reasons.empty:
        fig = px.bar(x=reasons.index, y=reasons.values, labels={"x": "Reason", "y": "Count"})
        st.plotly_chart(fig, use_container_width=True)

with tab4:
    st.markdown('<div class="section-label">Data Assets</div>', unsafe_allow_html=True)
    data_files = filtered[filtered["asset_type"] == "Data"]
    if len(data_files) > 0:
        st.dataframe(data_files[["filename", "format", "information_type", "domain"]].head(30), use_container_width=True)
    else:
        st.info("No data assets found")

st.divider()
st.caption("💡 Tip: Use the sidebar filters to explore different aspects of your project data.")
