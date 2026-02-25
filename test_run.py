"""
test_run.py — Verifies the 'core' pipeline with specific LLM settings.
Run from the 'urban-classifier/' root directory:
    python test_run.py
"""

import os
from pathlib import Path

# --- Import core pipeline functions ---
from core.pipeline import build_config, run

# ── LLM Settings (Direct Injection) ──────────────────────────────────────
# Note: Using direct assignment to ensure the pipeline receives the key
API_KEY = "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"
MODEL   = "google/gemini-2.0-flash-001"

# ── Project Configuration ────────────────────────────────────────────────
PROJECT = {
    "name":         "King Salman Park Masterplan",
    "location":     "Riyadh, Saudi Arabia",
    "year_range":   [2018, 2023],
    "lead_firm":    "Henning Larsen",
    "consultants":  ["MVA", "Happold", "Gerber", "COWI", "GHS", "FLB", "OMRANIA"],
    "authorities":  ["RCRC", "MOMRA", "MEWA", "SASO", "NFPA", "SEC"],
    "drawing_code": "KSP-[FIRM]-[PHASE]-[DISCIPLINE]-[TYPE]-[NUMBER]",
    "notes":        "Mixed-use urban masterplan. Internal files use KSP prefix.",
}

# ── Path Configuration ───────────────────────────────────────────────────
# ⚠️ Make sure this folder exists on your Mac
INPUT_PATH = Path.home() / "Desktop" / "Henning Larsen" / "2022Masterplan"
OUTPUT_CSV = Path("test_output.csv")

# ── Build Config ─────────────────────────────────────────────────────────
# We pass the API_KEY and MODEL directly here
config = build_config(
    project = PROJECT,
    model   = MODEL,
    api_key = API_KEY,
)

# ── Run Task for 20 Files ────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"--- Urban Classifier Test Run ---")
    print(f"Target Model: {MODEL}")
    
    if not INPUT_PATH.exists():
        print(f"❌ Error: Path not found at {INPUT_PATH}")
        print("   Please check if the '2022Masterplan' folder is on your Desktop.")
    else:
        print(f"🚀 Processing 20 files from: {INPUT_PATH.name}...")
        
        try:
            summary = run(
                input_path = INPUT_PATH,
                output_csv = OUTPUT_CSV,
                config     = config,
                sample_n   = 20,
            )
            print(f"✅ Success! Results saved to: {OUTPUT_CSV}")
            print(f"📝 Summary: {summary}")
            
        except Exception as e:
            print(f"❌ An error occurred during the run: {e}")
            print("   Check your internet connection or API quota.")