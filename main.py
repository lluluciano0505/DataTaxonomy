"""
main.py — All-in-one: Process Data → Dashboard
Configuration is read from config.yaml (no code edits needed!)

Run with:
    python main.py [--config config.yaml]
"""

import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv
import streamlit.web.cli as stcli

from config_loader import (
    load_config, get_project_config, get_paths_config,
    get_processing_config, get_dashboard_config,
    validate_input_path,
    load_taxonomy,
)

# ── Load environment ────────────────────────────────────────────────────
load_dotenv()

API_KEY = os.getenv("OPENROUTER_API_KEY")
if not API_KEY:
    print("❌ OPENROUTER_API_KEY not found in .env")
    sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="DataTaxonomy Pipeline")
    parser.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--parallel", type=int, default=1, help="Number of parallel workers (1=serial, >1=parallel)")
    args = parser.parse_args()
    
    # ── Load configuration ────────────────────────────────────────────────
    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as e:
        print(f"❌ Configuration error: {e}")
        sys.exit(1)
    
    project = get_project_config(config)
    paths = get_paths_config(config)
    processing = get_processing_config(config)
    dashboard_cfg = get_dashboard_config(config)
    
    # Override model if set in environment
    if "MODEL" in os.environ:
        processing["model"] = os.getenv("MODEL")
    
    # ── Validate input ────────────────────────────────────────────────────
    if not validate_input_path(paths["input_dir"]):
        print(f"❌ Cannot proceed. Check config.yaml paths.input_dir")
        sys.exit(1)
    
    # ── Step 1: Process Data ──────────────────────────────────────────────
    print("\n" + "="*70)
    print("🎯 DataTaxonomy Pipeline")
    print("="*70)
    print(f"📍 Project: {project['name']} ({project['location']})")
    print(f"📂 Input: {paths['input_dir'].name}")
    print(f"📊 Files to process: {processing.get('sample_n') or 'all'}")
    print("="*70 + "\n")
    
    if not process_data(paths, project, processing, API_KEY, args.parallel):
        print("⚠️ Data processing failed. Skipping dashboard.")
        sys.exit(1)
    
    # ── Step 2: Launch Dashboard ──────────────────────────────────────────
    try:
        launch_dashboard(dashboard_cfg)
    except KeyboardInterrupt:
        print("\n\n👋 Dashboard closed.")


def process_data(paths: dict, project: dict, processing: dict, api_key: str, parallel: int = 1) -> bool:
    """Run the pipeline and generate CSV."""
    from core.pipeline import build_config, run
    
    print("📊 STEP 1: Processing Files...")
    print("-" * 70)
    
    config = build_config(project=project, model=processing["model"], api_key=api_key)
        config["taxonomy"] = load_taxonomy()
    
    try:
        summary = run(
            input_path=paths["input_dir"],
            output_csv=paths["output_csv"],
            config=config,
            sample_n=processing.get("sample_n"),
            parallel=parallel,
        )
        print(f"\n✅ Success! Results saved to: {paths['output_csv']}")
        print(f"📝 Summary: {summary}\n")
        return True
    
    except Exception as e:
        print(f"❌ Error during processing: {e}")
        return False


def launch_dashboard(dashboard_cfg: dict) -> None:
    """Launch the Streamlit dashboard."""
    print("="*70)
    print("📈 STEP 2: Launching Dashboard...")
    print("="*70)
    print(f"🌐 Opening http://localhost:{dashboard_cfg['port']}\n")
    
    sys.argv = ["streamlit", "run", "dashboard.py", "--logger.level=error"]
    stcli.main()


if __name__ == "__main__":
    main()
