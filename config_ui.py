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
import re
import os
import json
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv()


def choose_directory_mac(prompt: str = "Select a folder") -> str | None:
    """Open native macOS folder picker and return selected POSIX path."""
    script = f'POSIX path of (choose folder with prompt "{prompt}")'
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            return None
        selected = result.stdout.strip()
        return selected or None
    except Exception:
        return None


def pick_directory_into_state(state_key: str, prompt: str, append_csv_filename: bool = False) -> None:
    """Open folder picker and write the chosen path into a Streamlit state key.
    If append_csv_filename is True, combines the chosen folder with the existing
    filename from state (or 'output.csv' as fallback) to preserve the .csv name.
    """
    selected_dir = choose_directory_mac(prompt)
    if selected_dir:
        selected_dir = selected_dir.rstrip("/")
        if append_csv_filename:
            existing = st.session_state.get(state_key, "")
            filename = Path(existing).name if existing and existing.lower().endswith(".csv") else "output.csv"
            st.session_state[state_key] = str(Path(selected_dir) / filename)
        else:
            st.session_state[state_key] = selected_dir
    else:
        st.session_state["path_picker_notice"] = "No folder selected."


def split_output_csv_path(raw_path: str) -> tuple[str, str]:
    """Split saved output_csv into folder + filename, correcting malformed repeated paths."""
    raw_path = (raw_path or "test_output.csv").strip()
    path_obj = Path(raw_path).expanduser()

    filename = path_obj.name or "test_output.csv"
    folder = "" if str(path_obj.parent) == "." else str(path_obj.parent)

    if folder.endswith(f"/{filename}") or folder == filename:
        folder = folder[:-(len(filename) + 1)] if folder.endswith(f"/{filename}") else ""

    return folder, filename


def build_output_csv_path(output_dir: str, output_name: str) -> str:
    """Build normalized output_csv path from folder + filename."""
    output_name = (output_name or "test_output.csv").strip() or "test_output.csv"
    if not output_name.lower().endswith(".csv"):
        output_name = f"{output_name}.csv"
    output_dir = (output_dir or "").strip()
    return str(Path(output_dir).expanduser() / output_name) if output_dir else output_name

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


def _scrape_page_text(url: str) -> str:
    """Scrape a URL with requests + BeautifulSoup and return clean readable text."""
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    # Remove noise tags
    for tag in soup(["script", "style", "nav", "footer", "header", "aside", "iframe", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text[:6000]  # keep within safe LLM context


def infer_project_config_from_url(url: str) -> dict:
    """Scrape a project page then ask the LLM to extract structured project metadata."""
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not set in .env — cannot call LLM.")

    page_text = _scrape_page_text(url)

    client = OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
    )

    prompt = f"""You are a project metadata extractor. Read the following webpage text about an architecture or urban design project and return ONLY a valid JSON object with these fields:

- name: project name (string)
- location: city and country (string, e.g. "Copenhagen, Denmark")
- year_range: [start_year, end_year] as integers (array of two ints)
- lead_firm: the main architecture/design firm (string)
- consultants: list of consultant firms or collaborators mentioned (array of strings)
- authorities: client or municipal authorities mentioned (array of strings)
- notes: a concise 1-2 sentence description of what the project is (string)

If a field is not found, use null for scalars and [] for arrays.
Return ONLY the JSON object, no markdown, no explanation.

Webpage text:
{page_text}"""

    response = client.chat.completions.create(
        model="google/gemini-2.0-flash-001",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )

    raw = response.choices[0].message.content.strip()
    # Strip markdown fences if present
    raw = re.sub(r"^```[a-z]*\n?", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\n?```$", "", raw)

    result = json.loads(raw)

    # Normalise types
    inferred: dict = {}
    if result.get("name"):
        inferred["name"] = str(result["name"])
    if result.get("location"):
        inferred["location"] = str(result["location"])
    yr = result.get("year_range")
    if isinstance(yr, list) and len(yr) == 2 and all(isinstance(y, int) for y in yr):
        inferred["year_range"] = yr
    if result.get("lead_firm"):
        inferred["lead_firm"] = str(result["lead_firm"])
    if isinstance(result.get("consultants"), list):
        inferred["consultants"] = [str(c) for c in result["consultants"] if c]
    if isinstance(result.get("authorities"), list):
        inferred["authorities"] = [str(a) for a in result["authorities"] if a]
    if result.get("notes"):
        inferred["notes"] = str(result["notes"])

    return inferred

# ── Display banner ─────────────────────────────────────────────────────────
try:
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
        st.caption("🚀 **Cloud Demo Version** - Configure your data taxonomy pipeline")
except Exception:
    st.title("⚙️ DataTaxonomy Configuration Manager")
    st.caption("🚀 **Cloud Demo Version** - Configure your data taxonomy pipeline")

st.divider()

config = load_config()

# ── Tabs for different config sections ─────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["📋 Project", "⚙️ Settings", "🗂️ Taxonomy"])

# ── TAB 1: Project Info ────────────────────────────────────────────────────
with tab1:
    st.subheader("Project Information")

    with st.expander("🌐 Auto-fill Project from URL", expanded=False):
        project_url = st.text_input(
            "Project URL",
            value="",
            placeholder="https://example.com/project-page",
            help="Paste a project webpage. The app will infer metadata and write into Project fields."
        )
        if st.button("✨ Auto-fill from URL", key="autofill_from_url", use_container_width=True):
            if not project_url.strip():
                st.warning("Please paste a valid URL first.")
            else:
                try:
                    inferred = infer_project_config_from_url(project_url.strip())
                    existing_project = config.get("project", {})

                    # Merge inferred values with existing values
                    merged_project = existing_project.copy()
                    for key in ["name", "location", "lead_firm", "notes", "year_range"]:
                        val = inferred.get(key)
                        if val:
                            merged_project[key] = val

                    existing_consultants = set(existing_project.get("consultants", []))
                    inferred_consultants = set(inferred.get("consultants", []))
                    if inferred_consultants:
                        merged_project["consultants"] = sorted(existing_consultants | inferred_consultants)

                    existing_authorities = set(existing_project.get("authorities", []))
                    inferred_authorities = set(inferred.get("authorities", []))
                    if inferred_authorities:
                        merged_project["authorities"] = sorted(existing_authorities | inferred_authorities)

                    config["project"] = merged_project
                    save_config(config)
                    st.info("Auto-filled project fields from URL. Review values below and click Save if needed.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not auto-fill from URL: {e}")
    
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

    st.divider()
    st.subheader("Project Paths")
    paths = config.get("paths", {})

    if "input_dir_value" not in st.session_state:
        st.session_state["input_dir_value"] = paths.get("input_dir", "")
    if "output_csv_value" not in st.session_state:
        st.session_state["output_csv_value"] = paths.get("output_csv", "test_output.csv")

    p1, p2 = st.columns(2)
    with p1:
        input_dir = st.text_input(
            "Input Directory",
            key="input_dir_value",
            help="Folder containing files to process"
        )
        st.button(
            "📂 Choose Input Folder",
            key="pick_input_dir",
            use_container_width=True,
            on_click=pick_directory_into_state,
            args=("input_dir_value", "Choose the input directory for processing"),
        )
    with p2:
        output_csv = st.text_input(
            "Output CSV",
            key="output_csv_value",
            help="Full path for the results CSV, e.g. /Users/me/project/output.csv"
        )
        st.button(
            "📁 Choose Output Folder",
            key="pick_output_dir",
            use_container_width=True,
            on_click=pick_directory_into_state,
            args=("output_csv_value", "Choose the output folder for results", True),
        )

    if st.session_state.get("path_picker_notice"):
        st.info(st.session_state.pop("path_picker_notice"))
    
    # Save button
    if st.button("💾 Save Project Info", key="save_project", use_container_width=True):
        config["project"] = {
            "name": project_name,
            "location": location,
            "year_range": [int(year_start), int(year_end)],
            "lead_firm": lead_firm,
            "consultants": [c.strip() for c in consultants_str.split(",") if c.strip()],
            "authorities": [a.strip() for a in authorities_str.split(",") if a.strip()],
            "notes": notes,
        }
        config["paths"] = {
            "input_dir": input_dir,
            "output_csv": output_csv,
        }
        save_config(config)

# ── TAB 2: Settings (Processing + age thresholds) ─────────────────────────
with tab2:
    processing = config.get("processing", {})
    age_analysis = config.get("age_analysis", {})

    col1, col2 = st.columns(2)
    with col1:
        sample_n = st.slider(
            "Files to Process",
            min_value=10,
            max_value=5000,
            value=processing.get("sample_n") or 20,
            step=10,
            help="Number of files to sample"
        )
        use_all = st.checkbox(
            "Process ALL files",
            value=processing.get("sample_n") is None,
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
        )

    with st.expander("🔧 Advanced", expanded=False):
        a1, a2, a3 = st.columns(3)
        with a1:
            parallel_workers = st.slider("Parallel Workers", 1, 16,
                value=processing.get("parallel_workers", 16), step=1)
        with a2:
            api_timeout = st.number_input("API Timeout (s)", 10, 300,
                value=processing.get("api_timeout", 30), step=10)
        with a3:
            warn_predates = st.number_input("Warn Predates (yrs)", 0, 100,
                value=age_analysis.get("warn_predates_years", 10))

    if st.button("💾 Save Settings", key="save_settings", use_container_width=True):
        config["processing"] = {
            "sample_n": None if use_all else sample_n,
            "model": model,
            "parallel_workers": parallel_workers,
            "api_timeout": api_timeout,
        }
        config["age_analysis"] = {
            "warn_predates_years": int(warn_predates),
            "warn_postproject_years": age_analysis.get("warn_postproject_years", 3),
        }
        save_config(config)

# ── Footer ─────────────────────────────────────────────────────────────────
# ── TAB 3: Taxonomy Editor ─────────────────────────────────────────────────
with tab3:
    import pandas as pd
    from config_loader import load_taxonomy, save_taxonomy

    TAXONOMY_PATH = Path("taxonomy.yaml")

    @st.cache_data
    def _load_tax():
        from config_loader import load_taxonomy as _lt
        return _lt()

    taxonomy_data = _load_tax()

    st.caption(
        "Define the classification options injected into the LLM prompt. "
        "Add, rename, or remove rows — changes apply on the next pipeline run."
    )

    SECTIONS = [
        ("domains",               "📁 Domains",               "Name your project's subject areas."),
        ("scales",                "🗺️ Scales",                "Geographic scope levels."),
        ("lifecycle_stages",      "📅 Lifecycle Stages",      "Design phase names used in your office."),
        ("confidentiality_levels","🔐 Confidentiality Levels","Access / sensitivity tiers."),
    ]

    edited_taxonomy = {}
    for key, label, hint in SECTIONS:
        st.subheader(label)
        st.caption(hint)
        items = taxonomy_data.get(key, [])
        df = pd.DataFrame(items) if items else pd.DataFrame(columns=["name", "description"])
        edited_df = st.data_editor(
            df,
            num_rows="dynamic",
            use_container_width=True,
            key=f"tax_{key}",
            column_config={
                "name":        st.column_config.TextColumn("Name",        width="medium"),
                "description": st.column_config.TextColumn("Description", width="large"),
            },
        )
        edited_taxonomy[key] = (
            edited_df.dropna(subset=["name"])
                     .where(edited_df.notna(), other=None)
                     .to_dict("records")
        )

    st.divider()
    if st.button("💾 Save Taxonomy", key="save_taxonomy_btn", use_container_width=True, type="primary"):
        save_taxonomy(edited_taxonomy)
        st.cache_data.clear()
        st.success("✅ Taxonomy saved to taxonomy.yaml — changes apply on next pipeline run.")

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
st.divider()

config = load_config()
parallel_workers = config.get("processing", {}).get("parallel_workers", 16)
sample_n = config.get("processing", {}).get("sample_n", 20)

st.markdown("""
<style>
    div[data-testid="stButton"] > button[kind="secondary"].run-btn {
        height: 3.5rem; font-size: 1.3rem;
    }
</style>
""", unsafe_allow_html=True)

if st.button("▶️  START PROCESSING", use_container_width=True, key="run_button", type="primary"):
    st.divider()
    
    st.write(f"📊 Running pipeline with **{parallel_workers}** parallel worker(s)...")
    
    # Build command (processing only; do not block by launching dashboard)
    cmd = ["python", "-u", "main.py", "--no-dashboard", "--parallel", str(parallel_workers)]
    
    # Progress tracking
    progress_bar = st.progress(0)
    status_text = st.empty()
    log_area = st.empty()
    
    try:
        status_text.write("⏳ Initializing pipeline...")
        progress_bar.progress(5)
        
        # Run process with real-time output capture
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        output_lines = []
        file_count = 0
        total_files = sample_n or 0
        
        # Read output line by line
        for line in process.stdout:
            output_lines.append(line.rstrip())
            
            # Update status based on output like: [0397/0400] filename ...
            m = re.search(r"\[(\d+)\/(\d+)\]", line)
            if m:
                file_count = max(file_count, int(m.group(1)))
                total_files = max(total_files, int(m.group(2)))
            
            # Estimate progress (0-95%)
            if total_files and total_files > 0:
                progress = min(95, int((file_count / total_files) * 90) + 5)
            else:
                progress = min(95, 5 + (len(output_lines) % 10))
            
            progress_bar.progress(progress)
            if total_files:
                status_text.write(f"🔄 Processing: {file_count}/{total_files} files processed...")
            else:
                status_text.write(f"🔄 Processing: {file_count} files processed...")
            
            # Show last 10 lines of output
            log_area.code("\n".join(output_lines[-10:]), language="text")
        
        # Wait for process to complete
        process.wait()
        
        # Display full log
        st.divider()
        with st.expander("📋 Full Processing Log", expanded=False):
            st.code("\n".join(output_lines), language="text")
        
        # Check result
        if process.returncode == 0:
            progress_bar.progress(100)
            status_text.success("✅ Processing completed successfully!")
            
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
                        st.info("🌐 Dashboard is available at http://localhost:8501")
                        st.markdown("""
                        **To view the dashboard:**
                        1. Open a new terminal
                        2. Run: `streamlit run dashboard.py`
                        3. Visit: http://localhost:8501
                        """)
                
                with col_next2:
                    if st.button("📁 Open Output Folder", use_container_width=True, key="open_folder"):
                        try:
                            subprocess.Popen(["open", str(output_csv.parent)])
                            st.success(f"📂 Opening {output_csv.parent}")
                        except Exception as e:
                            st.error(f"Could not open folder: {e}")
        else:
            progress_bar.progress(100)
            st.error(f"❌ Processing failed with code {process.returncode}")
    
    except subprocess.TimeoutExpired:
        progress_bar.progress(100)
        st.error("⏱️ Processing timed out (exceeded 1 hour)")
    except Exception as e:
        progress_bar.progress(100)
        st.error(f"❌ Error running pipeline: {e}")