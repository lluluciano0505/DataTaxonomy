"""
main.py — All-in-one: Process Data → Dashboard
Runs everything in one command:
    python main.py
"""

import os
import sys
import subprocess
from pathlib import Path
from dotenv import load_dotenv
import streamlit.web.cli as stcli

# ── Load environment ────────────────────────────────────────────────────
load_dotenv()

# ── LLM Settings ────────────────────────────────────────────────────────
API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL = os.getenv("MODEL", "google/gemini-2.0-flash-001")

if not API_KEY:
    print("❌ OPENROUTER_API_KEY not found. Please set it in .env")
    sys.exit(1)

# ── Project Configuration ───────────────────────────────────────────────
PROJECT = {
    "name": "Fælledby Masterplan",
    "location": "Copenhagen, Denmark",
    "year_range": [2019, 2026],
    "lead_firm": "Henning Larsen",
    "consultants": ["MOE", "BirdLife Denmark", "VIVA Landscape", "Niras"],
    "authorities": ["Copenhagen Municipality", "By & Havn", "Danish EPA"],
    "drawing_code": "FLB-[FIRM]-[PHASE]-[DISCIPLINE]-[TYPE]-[NUMBER]",
    "notes": "Timber-based rural-urban community. Focus on biodiversity and local ecology.",
}

# ── Paths ───────────────────────────────────────────────────────────────
INPUT_PATH = Path.home() / "Desktop" / "Henning Larsen" / "Fælledby"
OUTPUT_CSV = Path("test_output.csv")

# ── Step 1: Process Data ────────────────────────────────────────────────
def process_data():
    """Run the pipeline and generate CSV."""
    from core.pipeline import build_config, run

    print("\n" + "="*60)
    print("📊 STEP 1: Processing Files...")
    print("="*60)

    if not INPUT_PATH.exists():
        print(f"❌ Error: Path not found at {INPUT_PATH}")
        print("   Please check if the folder exists on your Desktop.")
        return False

    config = build_config(project=PROJECT, model=MODEL, api_key=API_KEY)

    try:
        print(f"🚀 Processing files from: {INPUT_PATH.name}")
        summary = run(
            input_path=INPUT_PATH,
            output_csv=OUTPUT_CSV,
            config=config,
            sample_n=20,  # Change to None for all files
        )
        print(f"✅ Success! Results saved to: {OUTPUT_CSV}")
        print(f"📝 Summary: {summary}\n")
        return True

    except Exception as e:
        print(f"❌ Error during processing: {e}")
        return False


# ── Step 2: Launch Dashboard ────────────────────────────────────────────
def launch_dashboard():
    """Launch the Streamlit dashboard."""
    print("="*60)
    print("📈 STEP 2: Launching Dashboard...")
    print("="*60)
    print("🌐 Opening browser at http://localhost:8501\n")

    # Run Streamlit
    sys.argv = ["streamlit", "run", "dashboard.py", "--logger.level=error"]
    stcli.main()


# ── Main Flow ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("\n🎯 Urban Asset Classifier — Full Pipeline")
    print(f"Project: {PROJECT['name']}")
    print(f"Location: {PROJECT['location']}\n")

    # Step 1: Process data
    if process_data():
        # Step 2: Launch dashboard
        try:
            launch_dashboard()
        except KeyboardInterrupt:
            print("\n\n👋 Dashboard closed.")
    else:
        print("⚠️ Data processing failed. Skipping dashboard.")
        sys.exit(1)
