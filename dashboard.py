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

# Sample data for demo purposes when CSV is not available
SAMPLE_DATA = [
    {
        "filename": "Project_Brief_2024.pdf",
        "format": "PDF", 
        "file_path": "/sample/project/Project_Brief_2024.pdf",
        "size_kb": 245,
        "extraction_coverage": "3/3 pages sampled",
        "is_data_hint": "Unlikely",
        "information_type": "Narrative / Textual",
        "domain": "Architecture & Buildings",
        "scale": "Building / Complex", 
        "lifecycle": "Concept Design",
        "asset_type": "Document",
        "governance": "Internal",
        "confidentiality": "Standard",
        "confidence": "High",
        "age_warning": "",
        "review_priority": "High",
        "action": "Auto-process",
        "review_reasons": "",
        "year": 2024,
        "short_summary": "Architectural project brief outlining design requirements and constraints.",
        "_reasoning": "Project brief document for architecture project.",
        "llm_status": "",
        "processed_at": "2026-03-05 12:00"
    },
    {
        "filename": "Site_Analysis.dwg", 
        "format": "DWG",
        "file_path": "/sample/project/Site_Analysis.dwg", 
        "size_kb": 1250,
        "extraction_coverage": "filename analysis only",
        "is_data_hint": "Likely",
        "information_type": "Spatial / Cartographic",
        "domain": "Urban Planning & Massing",
        "scale": "City / Municipal",
        "lifecycle": "Schematic Design", 
        "asset_type": "Data",
        "governance": "Internal",
        "confidentiality": "Standard",
        "confidence": "Medium",
        "age_warning": "",
        "review_priority": "Medium",
        "action": "Auto-process",
        "review_reasons": "",
        "year": 2024,
        "short_summary": "CAD drawing showing site analysis and urban context.",
        "_reasoning": "CAD file containing spatial data for urban planning.",
        "llm_status": "",
        "processed_at": "2026-03-05 12:01"
    },
    {
        "filename": "Budget_Estimates.xlsx",
        "format": "XLSX", 
        "file_path": "/sample/project/Budget_Estimates.xlsx",
        "size_kb": 89,
        "extraction_coverage": "5/5 sheets sampled",
        "is_data_hint": "Likely",
        "information_type": "Quantitative / Numerical",
        "domain": "Project Management", 
        "scale": "Non-spatial",
        "lifecycle": "Design Development",
        "asset_type": "Data", 
        "governance": "Internal",
        "confidentiality": "Confidential",
        "confidence": "High",
        "age_warning": "",
        "review_priority": "Critical", 
        "action": "Manual review",
        "review_reasons": "Contains budget information",
        "year": 2024,
        "short_summary": "Project budget estimates and cost breakdown.",
        "_reasoning": "Financial data requiring confidential handling.",
        "llm_status": "",
        "processed_at": "2026-03-05 12:02"
    },
    {
        "filename": "Environmental_Impact.pdf",
        "format": "PDF",
        "file_path": "/sample/project/Environmental_Impact.pdf", 
        "size_kb": 567,
        "extraction_coverage": "8/12 pages sampled",
        "is_data_hint": "Unlikely",
        "information_type": "Narrative / Textual",
        "domain": "Environment & Climate",
        "scale": "City / Municipal",
        "lifecycle": "Design Development",
        "asset_type": "Document", 
        "governance": "External",
        "confidentiality": "Standard",
        "confidence": "High",
        "age_warning": "",
        "review_priority": "High",
        "action": "Auto-process",
        "review_reasons": "",
        "year": 2023,
        "short_summary": "Environmental impact assessment for the development project.",
        "_reasoning": "Environmental compliance document from external consultant.",
        "llm_status": "",
        "processed_at": "2026-03-05 12:03"
    },
    {
        "filename": "Meeting_Notes_Dec2024.docx",
        "format": "DOCX",
        "file_path": "/sample/project/Meeting_Notes_Dec2024.docx",
        "size_kb": 156,
        "extraction_coverage": "full document sampled",
        "is_data_hint": "Unlikely",
        "information_type": "Narrative / Textual",
        "domain": "Project Management",
        "scale": "Non-spatial",
        "lifecycle": "Design Development",
        "asset_type": "Document",
        "governance": "Internal",
        "confidentiality": "Sensitive",
        "confidence": "Medium",
        "age_warning": "",
        "review_priority": "Medium",
        "action": "Auto-process",
        "review_reasons": "",
        "year": 2024,
        "short_summary": "Client meeting notes and project decisions from December 2024.",
        "_reasoning": "Internal meeting documentation with sensitive discussions.",
        "llm_status": "",
        "processed_at": "2026-03-05 12:04"
    },
    {
        "filename": "Structural_Calcs.pdf",
        "format": "PDF",
        "file_path": "/sample/project/Structural_Calcs.pdf",
        "size_kb": 892,
        "extraction_coverage": "4/15 pages sampled",
        "is_data_hint": "Likely",
        "information_type": "Quantitative / Numerical",
        "domain": "Architecture & Buildings",
        "scale": "Building / Complex",
        "lifecycle": "Design Development",
        "asset_type": "Data",
        "governance": "External",
        "confidentiality": "Standard",
        "confidence": "High",
        "age_warning": "",
        "review_priority": "Low",
        "action": "Auto-process",
        "review_reasons": "",
        "year": 2024,
        "short_summary": "Structural engineering calculations and analysis results.",
        "_reasoning": "Technical calculations from structural engineer consultant.",
        "llm_status": "",
        "processed_at": "2026-03-05 12:05"
    }
]

@st.cache_data
def load_data(path):
    try:
        if path.exists():
            df = pd.read_csv(path)
            df["year"] = pd.to_numeric(df["year"], errors="coerce")
            return df
        else:
            # Use sample data for demo
            st.info("📊 **Demo Mode**: Displaying sample data. Upload your own CSV file or run the pipeline locally to see real project data.")
            df = pd.DataFrame(SAMPLE_DATA)
            df["year"] = pd.to_numeric(df["year"], errors="coerce")
            return df
    except Exception as e:
        st.warning(f"Could not load CSV file: {e}. Using sample data instead.")
        df = pd.DataFrame(SAMPLE_DATA)
        df["year"] = pd.to_numeric(df["year"], errors="coerce")
        return df

# Load data (real or sample)
df = load_data(CSV_PATH)

st.title("Urban Asset Classifier — Project Dashboard")
st.caption(f"Source: {CSV_PATH} · {len(df)} files processed")
st.divider()

# Sidebar filters
st.sidebar.header("Filters")
all_domains    = sorted(df["domain"].dropna().unique())
all_scales     = sorted(df["scale"].dropna().unique())
all_lifecycles = sorted(df["lifecycle"].dropna().unique())
all_risks      = sorted(df["review_priority"].dropna().unique())

sel_domains    = st.sidebar.multiselect("Domain",     all_domains,    default=all_domains)
sel_scales     = st.sidebar.multiselect("Scale",      all_scales,     default=all_scales)
sel_lifecycles = st.sidebar.multiselect("Lifecycle",  all_lifecycles, default=all_lifecycles)
sel_risks      = st.sidebar.multiselect("Review Priority", all_risks,      default=all_risks)

filtered = df[
    df["domain"].isin(sel_domains) &
    df["scale"].isin(sel_scales) &
    df["lifecycle"].isin(sel_lifecycles) &
    df["review_priority"].isin(sel_risks)
]
st.sidebar.caption(f"Showing **{len(filtered)}** of {len(df)} files")

# Pre-compute counts
confidential_count = int((filtered["confidentiality"] == "Confidential").sum()) if "confidentiality" in filtered.columns else 0
sensitive_count    = int((filtered["confidentiality"] == "Sensitive").sum())    if "confidentiality" in filtered.columns else 0
data_count         = int((filtered["asset_type"] == "Data").sum())               if "asset_type" in filtered.columns else 0
non_data_count     = len(filtered) - data_count

# ROW 1: KPIs
left_kpi, gap, right_kpi = st.columns([3, 0.1, 2])

with left_kpi:
    st.markdown('<div class="section-label">Overview</div>', unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Files",   len(filtered))
    c2.metric("Critical Review", int((filtered["review_priority"] == "Critical").sum()))
    c3.metric("High Priority", int((filtered["review_priority"] == "High").sum()))
    c4.metric("Medium/Low",    int((filtered["review_priority"].isin(["Medium", "Low"])).sum()))

with right_kpi:
    st.markdown('<div class="section-label">Priority Flags</div>', unsafe_allow_html=True)
    conf_col, data_col = st.columns(2)
    with conf_col:
        st.metric("Confidential", confidential_count,
                  delta=f"+{sensitive_count} Sensitive", delta_color="off",
                  help="Confidential = contracts, fees, budgets, legal. Sensitive = drafts, memos, WIP.")
        if confidential_count > 0:
            pct = round(confidential_count / len(filtered) * 100) if len(filtered) else 0
            st.caption(f"{pct}% need access control")
    with data_col:
        st.metric("Data Assets", data_count,
                  delta=f"{non_data_count} non-data", delta_color="off",
                  help="asset_type = Data — spreadsheets, GIS layers, datasets")
        if data_count > 0:
            pct = round(data_count / len(filtered) * 100) if len(filtered) else 0
            st.caption(f"{pct}% are structured data")

st.divider()

# ROW 2: Data Assets + Confidentiality deep-dive
col_data, col_conf = st.columns(2)

with col_data:
    st.subheader("Data Assets")
    st.caption("Which formats and domains contain structured data")
    if "asset_type" in filtered.columns:
        data_files = filtered[filtered["asset_type"] == "Data"]
        if not data_files.empty:
            tab1, tab2 = st.tabs(["By Format", "By Domain"])
            with tab1:
                fmt_counts = data_files["format"].value_counts().reset_index()
                fmt_counts.columns = ["format", "count"]
                fig_fmt = px.bar(fmt_counts, x="count", y="format", orientation="h",
                                 color="count", color_continuous_scale="Blues",
                                 labels={"count": "Files", "format": ""})
                fig_fmt.update_layout(height=280, margin=dict(l=0,r=0,t=10,b=0), coloraxis_showscale=False)
                st.plotly_chart(fig_fmt, use_container_width=True)
            with tab2:
                dom_counts = data_files["domain"].value_counts().reset_index()
                dom_counts.columns = ["domain", "count"]
                fig_dom = px.bar(dom_counts, x="count", y="domain", orientation="h",
                                 color="count", color_continuous_scale="Blues",
                                 labels={"count": "Files", "domain": ""})
                fig_dom.update_layout(height=280, margin=dict(l=0,r=0,t=10,b=0), coloraxis_showscale=False)
                st.plotly_chart(fig_dom, use_container_width=True)
            with st.expander(f"View all {len(data_files)} data files"):
                data_show = [c for c in ["filename","format","domain","lifecycle","year","short_summary"] if c in data_files.columns]
                st.dataframe(data_files[data_show], use_container_width=True, height=250)
        else:
            st.info("No Data assets detected in current filter.")
    else:
        st.warning("asset_type column not found — re-run the pipeline.")

with col_conf:
    st.subheader("Confidentiality")
    st.caption("Sensitive and confidential files by domain")
    if "confidentiality" in filtered.columns:
        conf_colors = {"Confidential": "#e53e3e", "Sensitive": "#ed8936", "Standard": "#48bb78"}
        conf_order  = ["Confidential", "Sensitive", "Standard"]
        conf_domain = filtered.groupby(["domain","confidentiality"]).size().reset_index(name="count")
        if not conf_domain.empty:
            priority_order = (
                filtered[filtered["confidentiality"].isin(["Confidential","Sensitive"])]
                .groupby("domain").size().sort_values(ascending=True).index.tolist()
            )
            remaining    = [d for d in filtered["domain"].unique() if d not in priority_order]
            domain_order = remaining + priority_order
            fig_conf = px.bar(conf_domain, x="count", y="domain", color="confidentiality",
                              orientation="h", color_discrete_map=conf_colors,
                              category_orders={"confidentiality": conf_order, "domain": domain_order},
                              labels={"count": "Files", "domain": "", "confidentiality": ""})
            fig_conf.update_layout(height=300, margin=dict(l=0,r=0,t=10,b=0),
                                   legend=dict(orientation="h", yanchor="bottom", y=1.02))
            st.plotly_chart(fig_conf, use_container_width=True)
        conf_files = filtered[filtered["confidentiality"] == "Confidential"]
        sens_files = filtered[filtered["confidentiality"] == "Sensitive"]
        if not conf_files.empty:
            with st.expander(f"🔴 {len(conf_files)} Confidential files — review required"):
                conf_show = [c for c in ["filename","domain","lifecycle","action","year"] if c in conf_files.columns]
                st.dataframe(conf_files[conf_show], use_container_width=True, height=220)
        if not sens_files.empty:
            with st.expander(f"🟠 {len(sens_files)} Sensitive files"):
                sens_show = [c for c in ["filename","domain","lifecycle","year"] if c in sens_files.columns]
                st.dataframe(sens_files[sens_show], use_container_width=True, height=220)
        if conf_files.empty and sens_files.empty:
            st.success("No confidential or sensitive files in current filter.")
    else:
        st.warning("confidentiality column not found — re-run the pipeline.")

st.divider()

# ROW 3: Coverage Map + Trust Score
col1, col2 = st.columns([2, 1])

with col1:
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

with col2:
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

# ROW 4: Timeline + Priority Breakdown
col3, col4 = st.columns([2, 1])

with col3:
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

with col4:
    st.subheader("Review Priority")
    st.caption("By domain")
    risk_domain = filtered.groupby(["domain","review_priority"]).size().reset_index(name="count")
    risk_color  = {"Critical":"#c92a2a","Urgent":"#c92a2a","High":"#e74c3c","Medium":"#f39c12","Low":"#2ecc71"}
    if not risk_domain.empty:
        fig_risk = px.bar(risk_domain, x="count", y="domain", color="review_priority",
                          orientation="h", color_discrete_map=risk_color,
                          labels={"count":"Files","domain":"","review_priority":"Priority"})
        fig_risk.update_layout(margin=dict(l=0,r=0,t=30,b=0), height=350,
                               legend=dict(orientation="h", yanchor="bottom", y=1.02))
        st.plotly_chart(fig_risk, use_container_width=True)
    else:
        st.info("No data to display.")

st.divider()

# ROW 5: Full file table
st.subheader("File List")
show_cols = ["filename","file_path","domain","scale","lifecycle","asset_type","confidentiality",
             "governance","review_priority","confidence","year","short_summary"]
show_cols = [c for c in show_cols if c in filtered.columns]

priority_emoji = {"Critical":"🔴","Urgent":"🔴","High":"🟠","Medium":"🟡","Low":"🟢"}
conf_emoji = {"Confidential":"🔒","Sensitive":"🟠","Standard":""}

display_df = filtered[show_cols].copy()

# Quick file actions
st.subheader("📂 File Explorer")
st.caption("Select a file and open its folder location")

col1, col2 = st.columns(2)

with col1:
    selected_file = st.selectbox(
        "Select a file",
        options=filtered["filename"].tolist() if len(filtered) > 0 else [],
        index=None,
        placeholder="Choose a file..."
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
