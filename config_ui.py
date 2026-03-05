"""
config_ui.py — Web-based Configuration Manager + Pipeline Runner
Run with:
    streamlit run config_ui.py
"""

import streamlit as st
import yaml
from pathlib import Path
from datetime import datetime
import subprocess
import sys

# Page config
st.set_page_config(
    page_title="DataTaxonomy — Configuration",
    page_icon="⚙️",
    layout="wide",
)

# Custom styling
st.markdown("""
<style>
    [data-testid="stAppViewContainer"] { background: linear gradient(135deg, #f5f7fa 0%, #c3cfe2 100%); }
    .stTabs [data-baseweb="tab-list"] button { font-size: 16px; font-weight: 600; }
</style>
""", unsafe_allow_html=True)

CONFIG_PATH = Path("config.yaml")
PIC_PATH = Path("pic/DT.jpg")

# ── Load current config ────────────────────────────────────────────────────
@st.cache_data
def load_config():
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f)
    return {}

# ── Save config ────────────────────────────────────────────────────────────
def save_config(config: dict):
    with open(CONFIG_PATH, "w") as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    st.success("✅ Configuration saved!")
    st.cache_data.clear()

# ── Display banner ─────────────────────────────────────────────────────────
if PIC_PATH.exists():
    col1, col2 = st.columns([1, 2])
    with col1:
        st.image(str(PIC_PATH), use_container_width=True)
    with col2:
        st.title("🏙️ DataTaxonomy")
        st.subheader("Configuration Manager")
        st.caption(f"Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
else:
    st.title("⚙️ DataTaxonomy Configuration Manager")

st.divider()

config = load_config()

# ── Tabs for different config sections ─────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["📋 Project", "📂 Paths", "⚡ Processing", "🎨 Dashboard"])

# ── TAB 1: Project Info ────────────────────────────────────────────────────
with tab1:
    st.subheader("Project Information")
    
    col1, col2 = st.columns(2)
    
    with col1:
        project = config.get("project", {})
        
        project_name = st.text_input(
            "Project Name",
            value=project.get("name", ""),
            help="Your project's name"
        )
        
        location = st.text_input(
            "Location",
            value=project.get("location", ""),
            help="City, Country"
        )
        
        year_start = st.number_input(
            "Project Start Year",
            min_value=1900,
            max_value=2100,
            value=project.get("year_range", [2020, 2026])[0],
            step=1
        )
        
        year_end = st.number_input(
            "Project End Year",
            min_value=year_start,
            max_value=2100,
            value=project.get("year_range", [2020, 2026])[1],
            step=1
        )
    
    with col2:
        lead_firm = st.text_input(
            "Lead Firm",
            value=project.get("lead_firm", ""),
            help="Primary design/project lead"
        )
        
        consultants_str = ", ".join(project.get("consultants", []))
        consultants_str = st.text_area(
            "Consultants",
            value=consultants_str,
            help="Comma-separated list",
            height=100
        )
        
        authorities_str = ", ".join(project.get("authorities", []))
        authorities_str = st.text_area(
            "Authorities",
            value=authorities_str,
            help="Approving bodies (comma-separated)",
            height=100
        )
    
    notes = st.text_area(
        "Project Notes",
        value=project.get("notes", ""),
        help="Additional project information",
        height=80
    )
    
    drawing_code = st.text_input(
        "Drawing Code Format",
        value=project.get("drawing_code", ""),
        help="e.g., FLB-[FIRM]-[PHASE]-[DISCIPLINE]-[TYPE]-[NUMBER]"
    )
    
    # Save button
    if st.button("💾 Save Project Info", key="save_project", use_container_width=True):
        config["project"] = {
            "name": project_name,
            "location": location,
            "year_range": [int(year_start), int(year_end)],
            "lead_firm": lead_firm,
            "consultants": [c.strip() for c in consultants_str.split(",") if c.strip()],
            "authorities": [a.strip() for a in authorities_str.split(",") if a.strip()],
            "drawing_code": drawing_code,
            "notes": notes,
        }
        save_config(config)

# ── TAB 2: Paths ───────────────────────────────────────────────────────────
with tab2:
    st.subheader("File Paths")
    
    paths = config.get("paths", {})
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.info("💡 Use `~` for home directory or full absolute paths")
        input_dir = st.text_input(
            "Input Directory",
            value=paths.get("input_dir", ""),
            help="Folder containing files to process"
        )
    
    with col2:
        output_csv = st.text_input(
            "Output CSV File",
            value=paths.get("output_csv", ""),
            help="Where to save results"
        )
    
    if st.button("💾 Save Paths", key="save_paths", use_container_width=True):
        config["paths"] = {
            "input_dir": input_dir,
            "output_csv": output_csv,
        }
        save_config(config)

# ── TAB 3: Processing ──────────────────────────────────────────────────────
with tab3:
    st.subheader("Processing Settings")
    
    processing = config.get("processing", {})
    
    col1, col2 = st.columns(2)
    
    with col1:
        sample_n = st.slider(
            "Files to Process",
            min_value=10,
            max_value=5000,
            value=processing.get("sample_n", 20),
            step=10,
            help="Number of files to sample (null = all)"
        )
        
        use_all = st.checkbox(
            "Process ALL files",
            value=processing.get("sample_n") is None,
            help="Uncheck to use the slider value above"
        )
    
    with col2:
        models = [
            "google/gemini-2.0-flash-001",
            "google/gemini-1.5-flash",
            "anthropic/claude-3.5-sonnet",
            "anthropic/claude-3-opus",
            "openai/gpt-4-turbo",
        ]
        
        model = st.selectbox(
            "LLM Model",
            options=models,
            index=models.index(processing.get("model", "google/gemini-2.0-flash-001")),
            help="Choose the language model for classification"
        )
    
    st.divider()
    st.subheader("🎯 Advanced Options")
    
    col1, col2 = st.columns(2)
    
    with col1:
        parallel_workers = st.slider(
            "Parallel Workers",
            min_value=1,
            max_value=16,
            value=processing.get("parallel_workers", 1),
            step=1,
            help="Number of concurrent processes (1 = serial)"
        )
    
    with col2:
        api_timeout = st.number_input(
            "API Timeout (seconds)",
            min_value=10,
            max_value=300,
            value=processing.get("api_timeout", 30),
            step=10,
            help="How long to wait for LLM response"
        )
    
    if st.button("💾 Save Processing Settings", key="save_processing", use_container_width=True):
        config["processing"] = {
            "sample_n": None if use_all else sample_n,
            "model": model,
            "parallel_workers": parallel_workers,
            "api_timeout": api_timeout,
        }
        save_config(config)

# ── TAB 4: Dashboard & Analysis ────────────────────────────────────────────
with tab4:
    st.subheader("Dashboard Settings")
    
    dashboard = config.get("dashboard", {})
    age_analysis = config.get("age_analysis", {})
    
    col1, col2 = st.columns(2)
    
    with col1:
        port = st.number_input(
            "Dashboard Port",
            min_value=1024,
            max_value=65535,
            value=dashboard.get("port", 8502),
            step=1,
            help="Port number (default 8502)"
        )
        
        auto_launch = st.checkbox(
            "Auto-launch Browser",
            value=dashboard.get("auto_launch", True),
            help="Automatically open dashboard in browser"
        )
    
    with col2:
        warn_predates = st.number_input(
            "Warn if Predates (years)",
            min_value=0,
            max_value=100,
            value=age_analysis.get("warn_predates_years", 10),
            step=1,
            help="Flag files older than N years before project"
        )
        
        warn_postproject = st.number_input(
            "Warn if After Project (years)",
            min_value=0,
            max_value=100,
            value=age_analysis.get("warn_postproject_years", 3),
            step=1,
            help="Flag files N years after project end"
        )
    
    if st.button("💾 Save Dashboard Settings", key="save_dashboard", use_container_width=True):
        config["dashboard"] = {
            "port": int(port),
            "auto_launch": auto_launch,
        }
        config["age_analysis"] = {
            "warn_predates_years": int(warn_predates),
            "warn_postproject_years": int(warn_postproject),
        }
        save_config(config)

# ── Footer ─────────────────────────────────────────────────────────────────
st.divider()

col1, col2, col3 = st.columns([1, 1, 1])

with col1:
    if st.button("🔄 Reload Config", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

with col2:
    if st.button("📄 View Raw YAML", use_container_width=True):
        with open(CONFIG_PATH) as f:
            st.code(f.read(), language="yaml")

with col3:
    st.caption("✨ All changes saved to config.yaml")
st.divider()

# ── Run Pipeline Section ───────────────────────────────────────────────────
st.subheader("🚀 Run Pipeline")
st.caption("Process files with current configuration")

col_run1, col_run2, col_run3 = st.columns([1, 1, 1])

with col_run1:
    parallel_workers = st.slider(
        "Parallel Workers",
        min_value=1,
        max_value=16,
        value=4,
        step=1,
        key="run_parallel",
        help="Number of concurrent processes"
    )

with col_run2:
    no_dashboard = st.checkbox(
        "Skip Dashboard Launch",
        value=False,
        help="Don't launch dashboard after processing"
    )

with col_run3:
    st.empty()

# Run button
if st.button("▶️ START PROCESSING", use_container_width=True, key="run_button"):
    st.divider()
    
    config = load_config()
    sample_n = config.get("processing", {}).get("sample_n", 20)
    
    with st.spinner(f"⏳ Processing files (parallel={parallel_workers})..."):
        st.write("📊 Running pipeline...")
        
        # Build command
        cmd = ["python", "main.py", f"--parallel", str(parallel_workers)]
        if no_dashboard:
            cmd.append("--no-dashboard")
        
        try:
            # Run process and capture output
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )
            
            # Display output in a text area
            with st.expander("📋 Processing Log", expanded=True):
                if result.stdout:
                    st.code(result.stdout, language="text")
                if result.stderr:
                    st.warning("⚠️ Warnings/Errors:")
                    st.code(result.stderr, language="text")
            
            # Check result
            if result.returncode == 0:
                st.success("✅ Processing completed successfully!")
                
                # Show output file info
                output_csv = Path(config.get("paths", {}).get("output_csv", "test_output.csv"))
                if output_csv.exists():
                    file_size = output_csv.stat().st_size / 1024  # KB
                    st.info(f"📄 Output saved: `{output_csv}` ({file_size:.1f} KB)")
                    
                    # Offer to download
                    with open(output_csv) as f:
                        csv_data = f.read()
                    st.download_button(
                        label="⬇️ Download Results CSV",
                        data=csv_data,
                        file_name=output_csv.name,
                        mime="text/csv",
                        use_container_width=True
                    )
                    
                    # Next steps
                    st.divider()
                    st.subheader("📊 Next Steps")
                    
                    col_next1, col_next2 = st.columns(2)
                    
                    with col_next1:
                        if st.button("📈 Open Dashboard", use_container_width=True, key="open_dashboard"):
                            st.info("🌐 Dashboard will launch at http://localhost:8502")
                            st.markdown("""
                            **To view the dashboard:**
                            1. Open a new terminal
                            2. Run: `streamlit run dashboard.py`
                            3. Visit: http://localhost:8502
                            """)
                    
                    with col_next2:
                        if st.button("📁 Open Output Folder", use_container_width=True, key="open_folder"):
                            try:
                                subprocess.Popen(["open", str(output_csv.parent)])
                                st.success(f"📂 Opening {output_csv.parent}")
                            except Exception as e:
                                st.error(f"Could not open folder: {e}")
            else:
                st.error(f"❌ Processing failed with code {result.returncode}")
        
        except subprocess.TimeoutExpired:
            st.error("⏱️ Processing timed out (exceeded 1 hour)")
        except Exception as e:
            st.error(f"❌ Error running pipeline: {e}")