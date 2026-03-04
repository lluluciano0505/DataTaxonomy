"""
test_run.py — Verifies the 'core' pipeline with specific LLM settings.
Run from the 'urban-classifier/' root directory:
    python test_run.py
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ── Load environment variables from .env ─────────────────────────────────
load_dotenv()

# --- Import core pipeline functions ---
from core.pipeline import build_config, run

# ── LLM Settings (from .env) ──────────────────────────────────────────────
API_KEY = os.getenv("OPENROUTER_API_KEY")
MODEL   = os.getenv("MODEL", "google/gemini-2.0-flash-001")

if not API_KEY:
    raise EnvironmentError(
        "❌ OPENROUTER_API_KEY not found.\n"
        "   Please create a .env file with your key, or set the environment variable."
    )

# ── Project Configuration ────────────────────────────────────────────────
PROJECT = {
    "name":         "Fælledby Masterplan",
    "location":     "Copenhagen, Denmark",
    "year_range":   [2019, 2026],
    "lead_firm":    "Henning Larsen",
    "consultants":  ["MOE", "BirdLife Denmark", "VIVA Landscape", "Niras"],
    "authorities":  ["Copenhagen Municipality", "By & Havn", "Danish EPA"],
    "drawing_code": "FLB-[FIRM]-[PHASE]-[DISCIPLINE]-[TYPE]-[NUMBER]",
    "notes":        "Timber-based rural-urban community. Focus on biodiversity and local ecology.",
}

# ── Path Configuration ───────────────────────────────────────────────────
# ⚠️ Make sure this folder exists on your Mac
INPUT_PATH = Path.home() / "Desktop" / "Henning Larsen" / "Fælledby"
OUTPUT_CSV = Path("test_output.csv")

# ── Build Config ─────────────────────────────────────────────────────────
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
        print(f"🚀 Processing n files from: {INPUT_PATH.name}...")

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
