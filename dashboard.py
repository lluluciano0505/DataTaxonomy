"""
dashboard.py — Interactive Project Dashboard
Run with:
    streamlit run dashboard.py
"""

import pandas as pd
import streamlit as st
import plotly.express as px
from pathlib import Path
import subprocess
import os

from dotenv import load_dotenv
from openai import OpenAI

from config_loader import load_config as load_app_config
from core.layer4 import layer4_query

load_dotenv()

st.set_page_config(
    page_title = "Urban Asset Classifier — Dashboard",
    page_icon  = "🏙️",
    layout     = "wide",
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

CSV_PATH = Path("test_output.csv")

@st.cache_data
def load_data(path):
    try:
        if path.exists():
            df = pd.read_csv(path)
            df["year"] = pd.to_numeric(df["year"], errors="coerce")
            return df
        else:
            st.error(f"CSV not found: {path}. Please run the pipeline first.")
            st.stop()
    except Exception as e:
        st.error(f"Could not load CSV file: {e}")
        st.stop()

# Load data (real or sample)
df = load_data(CSV_PATH)
app_config = load_app_config()
layer4_model = app_config.get("processing", {}).get("model", os.getenv("MODEL", "google/gemini-2.0-flash-001"))
api_key = os.getenv("OPENROUTER_API_KEY")

st.title("Urban Asset Classifier — Project Dashboard")
st.caption(f"Source: {CSV_PATH} · {len(df)} files processed")
st.divider()

# Sidebar filters
st.sidebar.header("Filters")
all_domains    = sorted(df["domain"].dropna().unique())
all_scales     = sorted(df["scale"].dropna().unique())
all_lifecycles = sorted(df["lifecycle"].dropna().unique())

sel_domains    = st.sidebar.multiselect("Domain",     all_domains,    default=all_domains)
sel_scales     = st.sidebar.multiselect("Scale",      all_scales,     default=all_scales)
sel_lifecycles = st.sidebar.multiselect("Lifecycle",  all_lifecycles, default=all_lifecycles)

filtered = df[
    df["domain"].isin(sel_domains) &
    df["scale"].isin(sel_scales) &
    df["lifecycle"].isin(sel_lifecycles)
]
st.sidebar.caption(f"Showing **{len(filtered)}** of {len(df)} files")


def explain_row_reason(row) -> str:
    """Best-effort human explanation for why this file matters."""
    for key in ("review_reasons", "short_summary", "action"):
        val = row.get(key)
        if pd.notna(val) and str(val).strip():
            return str(val).strip()
    return "No explicit reason provided by pipeline output."


priority_need = pd.Series(False, index=filtered.index)
action_need = pd.Series(False, index=filtered.index)

if "review_priority" in filtered.columns:
    priority_need = filtered["review_priority"].isin(["Critical", "High", "Urgent"])

if "action" in filtered.columns:
    action_need = filtered["action"].fillna("").str.contains(r"manual|review", case=False, regex=True)

needs_review = filtered[priority_need | action_need].copy()
if not needs_review.empty:
    needs_review["reason"] = needs_review.apply(explain_row_reason, axis=1)

# Pre-compute counts
confidential_count = int((filtered["confidentiality"] == "Confidential").sum()) if "confidentiality" in filtered.columns else 0
sensitive_count    = int((filtered["confidentiality"] == "Sensitive").sum())    if "confidentiality" in filtered.columns else 0

# ROW 1: KPIs
st.markdown('<div class="section-label">Decision Snapshot</div>', unsafe_allow_html=True)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Files",   len(filtered))
c2.metric("Need Human Review", len(needs_review))
c3.metric("Confidential/Sensitive", confidential_count + sensitive_count)
c4.metric("No Immediate Review", max(len(filtered) - len(needs_review), 0))

st.divider()

# Layer 4: Ask the archive
st.markdown('<div class="section-label">Layer 4 Query</div>', unsafe_allow_html=True)
st.subheader("Ask the Archive")
st.caption("Ask a question against the current filtered files. Layer 4 will shortlist files, re-read them, and answer with evidence.")

query_default = st.session_state.get("layer4_question", "")
query_text = st.text_area(
    "Question",
    value=query_default,
    placeholder="例如：什么木材适合使用？ / 哪里提到清真寺？ / Which files mention hydrology constraints?",
    height=90,
    key="layer4_question_box",
)

if st.button("🔎 Run Layer 4 Query", use_container_width=True, type="primary", key="run_layer4_query"):
    st.session_state["layer4_question"] = query_text
    if not query_text.strip():
        st.warning("Please enter a question first.")
    elif filtered.empty:
        st.warning("No files are available under the current filters.")
    elif not api_key:
        st.error("OPENROUTER_API_KEY is missing. Add it to .env before using Layer 4.")
    else:
        with st.spinner("Layer 4 is searching, re-reading files, and synthesizing an answer..."):
            try:
                client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
                result = layer4_query(
                    question=query_text,
                    processed_df=filtered,
                    client=client,
                    model=layer4_model,
                )
                st.session_state["layer4_result"] = result
            except Exception as e:
                st.session_state["layer4_result"] = {
                    "question": query_text,
                    "answer": "Layer 4 query failed.",
                    "confidence": "Low",
                    "gaps": str(e),
                    "relevant_files": [],
                    "candidate_count": 0,
                    "deep_read_count": 0,
                    "search_plan": {},
                    "candidates": [],
                }

layer4_result = st.session_state.get("layer4_result")
if layer4_result:
    r1, r2 = st.columns([3, 1])
    with r1:
        st.markdown("**Answer**")
        st.write(layer4_result.get("answer", ""))
        if layer4_result.get("gaps"):
            st.caption(f"Gaps / uncertainty: {layer4_result.get('gaps')}")
    with r2:
        st.metric("Confidence", layer4_result.get("confidence", "Low"))
        st.metric("Candidate Files", layer4_result.get("candidate_count", 0))
        st.metric("Deep Read Files", layer4_result.get("deep_read_count", 0))

    relevant_files = layer4_result.get("relevant_files", [])
    if relevant_files:
        st.markdown("**Relevant Files**")
        st.dataframe(pd.DataFrame(relevant_files), use_container_width=True, height=240)

    with st.expander("Show retrieval details", expanded=False):
        search_plan = layer4_result.get("search_plan", {})
        if search_plan:
            st.json(search_plan)
        candidates = layer4_result.get("candidates", [])
        if candidates:
            st.dataframe(pd.DataFrame(candidates), use_container_width=True, height=220)

st.divider()

# ROW 2: Structure overview
st.markdown('<div class="section-label">Structure</div>', unsafe_allow_html=True)

st.subheader("Coverage Map")
st.caption("Files per Domain x Scale — empty cells = data gaps")
coverage = filtered.groupby(["domain","scale"]).size().reset_index(name="count")
if not coverage.empty:
    pivot = coverage.pivot(index="domain", columns="scale", values="count").fillna(0)
    fig_heat = px.imshow(pivot, text_auto=True, color_continuous_scale="Blues",
                         labels=dict(color="Files"), aspect="auto")
    fig_heat.update_layout(margin=dict(l=0,r=0,t=30,b=0), height=380,
                           xaxis_title="", yaxis_title="", coloraxis_showscale=False)
    fig_heat.update_xaxes(tickangle=-30)
    st.plotly_chart(fig_heat, use_container_width=True)
else:
    st.info("No data to display.")

st.divider()

st.subheader("Timeline View")
st.caption("Files per year, coloured by Lifecycle stage")
timeline_df = filtered.dropna(subset=["year"]).copy()
timeline_df["year"] = timeline_df["year"].astype(int)
if not timeline_df.empty:
    timeline = timeline_df.groupby(["year","lifecycle"]).size().reset_index(name="count")
    fig_time = px.bar(timeline, x="year", y="count", color="lifecycle", barmode="stack",
                      labels={"count":"Files","year":"Year","lifecycle":"Lifecycle"})
    fig_time.update_layout(margin=dict(l=0,r=0,t=30,b=0), height=350,
                           xaxis=dict(dtick=1),
                           legend=dict(orientation="h", yanchor="bottom", y=1.02))
    st.plotly_chart(fig_time, use_container_width=True)
    oldest = timeline_df["year"].min()
    newest = timeline_df["year"].max()
    if newest - oldest > 5:
        st.warning(f"Data spans {int(oldest)}-{int(newest)} ({int(newest-oldest)} years) — check old files.")
else:
    st.info("No year data available.")

st.divider()

# ROW 3: Data inventory
st.markdown('<div class="section-label">Data Inventory</div>', unsafe_allow_html=True)
st.subheader("Data Assets")
if "asset_type" in filtered.columns:
    data_files = filtered[filtered["asset_type"] == "Data"].copy()
    if not data_files.empty:
        detail_cols = [c for c in ["filename", "domain", "lifecycle", "format", "short_summary", "review_priority", "year"] if c in data_files.columns]
        st.dataframe(data_files[detail_cols], use_container_width=True, height=320)
    else:
        st.info("No Data assets detected in current filter.")
else:
    st.warning("asset_type column not found — re-run the pipeline.")

st.divider()

# ROW 4: Risk & governance
st.markdown('<div class="section-label">Risk & Governance</div>', unsafe_allow_html=True)
col_conf, col_trust = st.columns([2, 1])

with col_conf:
    st.subheader("Confidentiality")
    if "confidentiality" in filtered.columns:
        flagged = filtered[filtered["confidentiality"].isin(["Confidential", "Sensitive"])].copy()
        if not flagged.empty:
            flagged["reason"] = flagged.apply(explain_row_reason, axis=1)
            conf_rank = {"Confidential": 0, "Sensitive": 1}
            flagged["_rank"] = flagged["confidentiality"].map(conf_rank).fillna(9)
            flagged = flagged.sort_values(["_rank", "review_priority", "domain"], ascending=[True, True, True])

            overview_cols = [c for c in ["filename", "confidentiality", "review_priority", "domain", "reason"] if c in flagged.columns]
            st.markdown("**Files needing access attention**")
            st.dataframe(flagged[overview_cols], use_container_width=True, height=320)
        else:
            st.success("No confidential or sensitive files in current filter.")
    else:
        st.warning("confidentiality column not found — re-run the pipeline.")

with col_trust:
    st.subheader("Trust Score")
    st.caption("Governance breakdown")
    trust = filtered["governance"].value_counts().reset_index()
    trust.columns = ["governance", "count"]
    color_map = {"Official":"#2ecc71","Internal":"#3498db","External":"#e67e22","Unknown":"#e74c3c"}
    if not trust.empty:
        fig_trust = px.pie(trust, names="governance", values="count",
                           color="governance", color_discrete_map=color_map, hole=0.45)
        fig_trust.update_traces(textposition="inside", textinfo="percent+label")
        fig_trust.update_layout(showlegend=False, margin=dict(l=0,r=0,t=30,b=0), height=380)
        st.plotly_chart(fig_trust, use_container_width=True)
        unknown_pct = int(trust.loc[trust["governance"]=="Unknown","count"].sum() / len(filtered) * 100) if len(filtered) else 0
        if unknown_pct > 30:
            st.warning(f"{unknown_pct}% of files have unknown governance.")
        else:
            st.success(f"{100 - unknown_pct}% of files have identified sources.")
    else:
        st.info("No data to display.")

st.divider()

st.subheader("Need Human Review")
if not needs_review.empty:
    review_cols = [c for c in ["filename", "domain", "lifecycle", "review_priority", "reason"] if c in needs_review.columns]
    st.dataframe(needs_review[review_cols], use_container_width=True, height=260)
else:
    st.success("No files currently flagged for review in this filter.")

st.divider()

# Quick file actions
st.subheader("📂 File Explorer")
st.caption("Select a file and open its folder location")

col1, col2 = st.columns(2)

file_options = []
if len(filtered) > 0 and "filename" in filtered.columns:
    file_options = [str(x) for x in filtered["filename"].dropna().tolist()]
    # Deduplicate while preserving order
    file_options = list(dict.fromkeys(file_options))

with col1:
    if not file_options:
        st.warning("当前筛选结果没有文件可检阅。请先调整左侧 Filters。")
        selected_file = None
    else:
        selected_file = st.selectbox(
            "Select a file",
            options=file_options,
            index=0,
        )
    
    if selected_file:
        file_info = filtered[filtered["filename"] == selected_file].iloc[0]
        file_path = file_info.get("file_path")
        
        btn_col1, btn_col2 = st.columns(2)
        
        with btn_col1:
            if st.button("📂 Open Folder", key="open_folder", use_container_width=True):
                try:
                    # macOS: open folder containing the file
                    folder_path = str(Path(file_path).parent)
                    subprocess.Popen(["open", folder_path])
                    st.success(f"📂 Opening folder: {Path(file_path).parent.name}/")
                except Exception as e:
                    st.error(f"Error: {e}")
        
        with btn_col2:
            if st.button("📁 Show in Finder", key="show_in_finder", use_container_width=True):
                try:
                    # macOS: open -R highlights the file in Finder
                    subprocess.Popen(["open", "-R", file_path])
                    st.success(f"✨ Highlighting {Path(file_path).name} in Finder...")
                except Exception as e:
                    st.error(f"Error: {e}")

with col2:
    if selected_file:
        file_info = filtered[filtered["filename"] == selected_file].iloc[0]
        st.metric("Filename", Path(file_info.get("file_path", "")).name)
        st.caption(f"**Size:** {file_info.get('size_kb', '—')} KB")
        st.caption(f"**Type:** {file_info.get('format', '—')}")
        st.caption(f"**Priority:** {file_info.get('review_priority', '—')}")
    else:
        st.info("请选择一个文件查看详情。")

st.divider()

# File table with paths displayed
st.subheader("📋 File List")
show_cols = ["filename", "file_path", "domain", "scale", "lifecycle", "asset_type", "confidentiality",
             "governance", "review_priority", "confidence", "year", "short_summary"]
show_cols = [c for c in show_cols if c in filtered.columns]

priority_emoji = {"Critical":"🔴","Urgent":"🔴","High":"🟠","Medium":"🟡","Low":"🟢"}
conf_emoji = {"Confidential":"🔒","Sensitive":"🟠","Standard":""}

display_df = filtered[show_cols].copy()

display_df["review_priority"] = display_df["review_priority"].map(lambda x: f"{priority_emoji.get(x,'')} {x}")
if "confidentiality" in display_df.columns:
    display_df["confidentiality"] = display_df["confidentiality"].map(
        lambda x: f"{conf_emoji.get(x,'')} {x}".strip()
    )

# Display file paths as plain text (not clickable)
st.dataframe(
    display_df, 
    use_container_width=True, 
    height=400,
    column_config={
        "file_path": st.column_config.TextColumn(
            "File Path",
            width="large",
            help="Full path to the file"
        ),
        "filename": st.column_config.TextColumn(
            "File Name",
            width="medium"
        ),
        "short_summary": st.column_config.TextColumn(
            "Summary",
            width="large"
        )
    }
)

csv_bytes = filtered.to_csv(index=False).encode("utf-8")
st.download_button(label="Download filtered CSV", data=csv_bytes,
                   file_name="filtered_output.csv", mime="text/csv")
