"""
dashboard.py — Interactive Project Dashboard
Run with:
    streamlit run dashboard.py
"""

import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path

# ── Page config ───────────────────────────────────────────────────────────
st.set_page_config(
    page_title  = "Urban Asset Classifier — Dashboard",
    page_icon   = "🏙️",
    layout      = "wide",
)

# ── Load data ─────────────────────────────────────────────────────────────
CSV_PATH = Path("test_output.csv")

@st.cache_data
def load_data(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["year"] = pd.to_numeric(df["year"], errors="coerce")
    return df

if not CSV_PATH.exists():
    st.error(f"❌ Could not find `{CSV_PATH}`. Run `python test_run.py` first.")
    st.stop()

df = load_data(CSV_PATH)

# ── Header ────────────────────────────────────────────────────────────────
st.title("🏙️ Urban Asset Classifier — Project Dashboard")
st.caption(f"Source: `{CSV_PATH}` · {len(df)} files processed")

st.divider()

# ── Sidebar filters ───────────────────────────────────────────────────────
st.sidebar.header("🔍 Filters")

all_domains    = sorted(df["domain"].dropna().unique())
all_scales     = sorted(df["scale"].dropna().unique())
all_lifecycles = sorted(df["lifecycle"].dropna().unique())
all_risks      = sorted(df["risk_level"].dropna().unique())

sel_domains    = st.sidebar.multiselect("Domain",     all_domains,    default=all_domains)
sel_scales     = st.sidebar.multiselect("Scale",      all_scales,     default=all_scales)
sel_lifecycles = st.sidebar.multiselect("Lifecycle",  all_lifecycles, default=all_lifecycles)
sel_risks      = st.sidebar.multiselect("Risk Level", all_risks,      default=all_risks)

filtered = df[
    df["domain"].isin(sel_domains) &
    df["scale"].isin(sel_scales) &
    df["lifecycle"].isin(sel_lifecycles) &
    df["risk_level"].isin(sel_risks)
]

st.sidebar.caption(f"Showing **{len(filtered)}** of {len(df)} files")

# ── KPI row ───────────────────────────────────────────────────────────────
k1, k2, k3, k4, k5, k6, k7 = st.columns(7)

k1.metric("Total Files",    len(filtered))
k2.metric("🔴 High Risk",   int((filtered["risk_level"] == "High").sum()))
k3.metric("🟡 Medium Risk", int((filtered["risk_level"] == "Medium").sum()))
k4.metric("🟢 Low Risk",    int((filtered["risk_level"] == "Low").sum()))
k5.metric("LLM Failures",   int(filtered["llm_status"].notna().sum() if "llm_status" in filtered.columns else 0))

confidential_count = int((filtered["confidentiality"] == "Confidential").sum()) if "confidentiality" in filtered.columns else 0
data_count         = int((filtered["asset_type"] == "Data").sum()) if "asset_type" in filtered.columns else 0

k6.metric("🔒 Confidential", confidential_count,
          help="Files classified as Confidential — contracts, fees, budgets, legal agreements")
k7.metric("🗄️ Data Assets",  data_count,
          help="Files classified as asset_type = Data — spreadsheets, GIS layers, datasets")

st.divider()

# ── Row 1: Coverage Map + Trust Score ────────────────────────────────────
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("📊 Coverage Map")
    st.caption("Files per Domain × Scale — empty cells = data gaps")

    coverage = (
        filtered.groupby(["domain", "scale"])
        .size()
        .reset_index(name="count")
    )

    if not coverage.empty:
        pivot = coverage.pivot(index="domain", columns="scale", values="count").fillna(0)
        fig_heat = px.imshow(
            pivot,
            text_auto = True,
            color_continuous_scale = "Blues",
            labels = dict(color="Files"),
            aspect = "auto",
        )
        fig_heat.update_layout(
            margin       = dict(l=0, r=0, t=30, b=0),
            height       = 380,
            xaxis_title  = "",
            yaxis_title  = "",
            coloraxis_showscale = False,
        )
        fig_heat.update_xaxes(tickangle=-30)
        st.plotly_chart(fig_heat, use_container_width=True)
    else:
        st.info("No data to display.")

with col2:
    st.subheader("🏛️ Trust Score")
    st.caption("Governance breakdown")

    trust = filtered["governance"].value_counts().reset_index()
    trust.columns = ["governance", "count"]

    color_map = {
        "Official": "#2ecc71",
        "Internal": "#3498db",
        "External": "#e67e22",
        "Unknown":  "#e74c3c",
    }

    if not trust.empty:
        fig_trust = px.pie(
            trust,
            names  = "governance",
            values = "count",
            color  = "governance",
            color_discrete_map = color_map,
            hole   = 0.45,
        )
        fig_trust.update_traces(textposition="inside", textinfo="percent+label")
        fig_trust.update_layout(
            showlegend = False,
            margin     = dict(l=0, r=0, t=30, b=0),
            height     = 380,
        )
        st.plotly_chart(fig_trust, use_container_width=True)

        # Insight
        unknown_pct = int(trust.loc[trust["governance"] == "Unknown", "count"].sum() / len(filtered) * 100) if len(filtered) else 0
        if unknown_pct > 30:
            st.warning(f"⚠️ {unknown_pct}% of files have unknown governance — verify sources.")
        else:
            st.success(f"✅ {100 - unknown_pct}% of files have identified sources.")
    else:
        st.info("No data to display.")

st.divider()

# ── Row 2: Timeline + Risk breakdown ────────────────────────────────────
col3, col4 = st.columns([2, 1])

with col3:
    st.subheader("📅 Timeline View")
    st.caption("Files per year, coloured by Lifecycle stage")

    timeline_df = filtered.dropna(subset=["year"]).copy()
    timeline_df["year"] = timeline_df["year"].astype(int)

    if not timeline_df.empty:
        timeline = (
            timeline_df.groupby(["year", "lifecycle"])
            .size()
            .reset_index(name="count")
        )
        fig_time = px.bar(
            timeline,
            x        = "year",
            y        = "count",
            color    = "lifecycle",
            barmode  = "stack",
            labels   = {"count": "Files", "year": "Year", "lifecycle": "Lifecycle"},
        )
        fig_time.update_layout(
            margin    = dict(l=0, r=0, t=30, b=0),
            height    = 350,
            xaxis     = dict(dtick=1),
            legend    = dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig_time, use_container_width=True)

        # Insight — oldest year
        oldest = timeline_df["year"].min()
        newest = timeline_df["year"].max()
        if newest - oldest > 5:
            st.warning(f"⚠️ Data spans {int(oldest)}–{int(newest)} ({int(newest-oldest)} years) — check if old files are still relevant.")
    else:
        st.info("No year data available.")

with col4:
    st.subheader("🚦 Risk Breakdown")
    st.caption("By domain")

    risk_domain = (
        filtered.groupby(["domain", "risk_level"])
        .size()
        .reset_index(name="count")
    )

    risk_color = {"High": "#e74c3c", "Medium": "#f39c12", "Low": "#2ecc71"}

    if not risk_domain.empty:
        fig_risk = px.bar(
            risk_domain,
            x                  = "count",
            y                  = "domain",
            color              = "risk_level",
            orientation        = "h",
            color_discrete_map = risk_color,
            labels             = {"count": "Files", "domain": "", "risk_level": "Risk"},
        )
        fig_risk.update_layout(
            margin  = dict(l=0, r=0, t=30, b=0),
            height  = 350,
            legend  = dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig_risk, use_container_width=True)
    else:
        st.info("No data to display.")

st.divider()

# ── Row 3: File table ─────────────────────────────────────────────────────
st.subheader("📁 File List")

show_cols = [
    "filename", "domain", "scale", "lifecycle",
    "asset_type", "governance", "risk_level",
    "confidence", "year", "short_summary",
]
show_cols = [c for c in show_cols if c in filtered.columns]

risk_emoji = {"High": "🔴", "Medium": "🟡", "Low": "🟢"}
display_df = filtered[show_cols].copy()
display_df["risk_level"] = display_df["risk_level"].map(lambda x: f"{risk_emoji.get(x,'')} {x}")

st.dataframe(display_df, use_container_width=True, height=400)

# Download button
csv_bytes = filtered.to_csv(index=False).encode("utf-8")
st.download_button(
    label     = "⬇️ Download filtered CSV",
    data      = csv_bytes,
    file_name = "filtered_output.csv",
    mime      = "text/csv",
)
