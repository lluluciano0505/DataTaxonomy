import os
import csv
import time
import random
from datetime import datetime
from pathlib import Path
from typing import Optional

from openai import OpenAI

from .layer1 import layer1_technical, INFO_TYPE_MAP
from .layer2 import layer2_domain
from .layer3 import layer3_trust

# ── Supported file formats ────────────────────────────────────────────────
SUPPORTED_FORMATS = {
    ".pdf", ".docx", ".doc", ".txt", ".pptx",
    ".xlsx", ".xls", ".csv", ".json",
    ".dwg", ".dxf", ".ifc", ".rvt",
    ".jpg", ".jpeg", ".png", ".tiff", ".tif",
    ".shp", ".geojson", ".kml",
    ".eml", ".msg", ".zip",
}

# ── CSV output columns ────────────────────────────────────────────────────
FIELDNAMES = [
    "filename", "format", "file_path", "size_kb",
    "extraction_coverage", "is_data_hint",
    "information_type", "year", "domain", "scale", "lifecycle",
    "asset_type", "short_summary",
    "governance", "confidentiality", "confidence",
    "age_warning", "risk_level", "action", "review_reasons",
    "llm_status", "processed_at",
]


# ── Config loader — reads from env or explicit dict ───────────────────────
def build_config(project: dict, model: str, api_key: str) -> dict:
    """
    Packages everything the pipeline needs into a single config dict.
    Use this instead of relying on notebook globals.

    project   — same dict as PROJECT in the notebook
    model     — OpenRouter model string
    api_key   — OpenRouter API key
    """
    p           = project
    consultants = ", ".join(p.get("consultants", []))
    authorities = ", ".join(p.get("authorities", []))
    yr          = p.get("year_range", [])
    year_str    = f"{yr[0]}–{yr[1]}" if len(yr) == 2 else "unknown"

    project_context = (
        f"Project: {p.get('name', 'Unknown')} | "
        f"Location: {p.get('location', 'Unknown')} | "
        f"Years: {year_str} | "
        f"Lead firm: {p.get('lead_firm', 'Unknown')} | "
        f"Consultants: {consultants} | "
        f"Authorities: {authorities} | "
        f"Drawing code format: {p.get('drawing_code', 'Unknown')} | "
        f"Notes: {p.get('notes', '')}"
    )

    return {
        "project":         project,
        "project_context": project_context,
        "model":           model,
        "api_key":         api_key,
        "base_url":        "https://openrouter.ai/api/v1",
        "temperature":     0,
        "delay":           0.3,
    }


# ── Single file processor ─────────────────────────────────────────────────
def process_file(file_path: Path, client: OpenAI, config: dict) -> dict:
    """
    Runs all three layers on a single file.
    Returns a flat dict ready to be written as a CSV row.
    """
    l1 = layer1_technical(file_path)

    l2 = layer2_domain(
        meta            = l1,
        client          = client,
        model           = config["model"],
        input_path      = config["input_path"],
        project_context = config["project_context"],
        temperature     = config["temperature"],
    )

    l3 = layer3_trust(
        file_path = file_path,
        meta      = l1,
        layer2    = l2,
        project   = config["project"],
    )

    llm_raw    = str(l2.get("llm", ""))
    llm_status = llm_raw if llm_raw.startswith("error") else ""

    return {
        # Identity
        "filename":            l1["filename"],
        "format":              l1["format"],
        "file_path":           l1["file_path"],
        "size_kb":             l1["size_kb"],
        # Layer 1
        "extraction_coverage": l1.get("extraction_coverage", ""),
        "is_data_hint":        l1.get("is_data_hint", "Unlikely"),
        # Layer 2
        "information_type":    l2.get("information_type", l1["information_type"]),
        "year":                l2.get("year") or l1.get("year"),
        "domain":              l2.get("domain",    "Unknown"),
        "scale":               l2.get("scale",     "Unknown"),
        "lifecycle":           l2.get("lifecycle", "Unknown"),
        "asset_type":          l2.get("asset_type", "Unknown"),
        "short_summary":       l2.get("short_summary", ""),
        # Layer 3
        "governance":          l3["governance"],
        "confidentiality":     l3["confidentiality"],
        "confidence":          l2.get("confidence", "Low"),
        "age_warning":         l3["age_warning"],
        "risk_level":          l3["risk_level"],
        "action":              l3["action"],
        "review_reasons":      l3["review_reasons"],
        # Meta
        "llm_status":          llm_status,
        "processed_at":        datetime.now().strftime("%Y-%m-%d %H:%M"),
    }


# ── Batch runner ──────────────────────────────────────────────────────────
def run(
    input_path:  Path,
    output_csv:  Path,
    config:      dict,
    sample_n:    Optional[int] = None,
    on_progress: Optional[callable] = None,
) -> dict:
    """
    Processes all supported files under input_path and writes output_csv.

    on_progress(i, total, row) — optional callback for progress updates.
    Used by the FastAPI/Celery layer to push status to the frontend.

    Returns a summary dict.
    """
    config = {**config, "input_path": input_path}   # inject input_path

    # ── Collect files ─────────────────────────────────────────────────────
    all_files = [
        p for p in input_path.rglob("*")
        if p.is_file() and p.suffix.lower() in SUPPORTED_FORMATS
    ]

    if sample_n and sample_n < len(all_files):
        files       = random.sample(all_files, sample_n)
        scope_label = f"SAMPLE {sample_n} of {len(all_files)}"
    else:
        files       = all_files
        scope_label = f"ALL {len(all_files)}"

    # ── LLM client ────────────────────────────────────────────────────────
    client = OpenAI(api_key=config["api_key"], base_url=config["base_url"])

    print(f"""
=================================================================
  Urban Asset Classifier — 3 Layers
  Input:  {input_path}
  Scope:  {scope_label}
  Output: {output_csv}
=================================================================
""")

    # ── Process + write CSV ───────────────────────────────────────────────
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    ok_count = error_count = llm_fail_count = 0
    risk_counts = {"High": 0, "Medium": 0, "Low": 0}
    start_time  = time.time()

    with open(output_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES, extrasaction="ignore")
        writer.writeheader()

        for i, fp in enumerate(files, 1):
            elapsed  = time.time() - start_time
            eta_secs = int((elapsed / i) * (len(files) - i)) if i > 1 else 0
            eta_str  = f"{eta_secs//60}m{eta_secs%60:02d}s" if i > 1 else "--"
            print(f"[{i:04d}/{len(files)}] {fp.name:<55} ETA {eta_str} ", end="", flush=True)

            try:
                row = process_file(fp, client, config)
                writer.writerow(row)
                f.flush()
                risk   = row["risk_level"]
                domain = row["domain"][:20]
                print(f"✓  {domain:<20} | {risk}")
                ok_count += 1
                risk_counts[risk] = risk_counts.get(risk, 0) + 1
                if row.get("llm_status"):
                    llm_fail_count += 1
                if on_progress:
                    on_progress(i, len(files), row)
            except Exception as e:
                print(f"✗  ERROR: {e}")
                error_count += 1

            time.sleep(config["delay"])

    total_time = int(time.time() - start_time)
    summary = {
        "scope":        scope_label,
        "total":        ok_count,
        "errors":       error_count,
        "llm_failures": llm_fail_count,
        "risk_high":    risk_counts.get("High",   0),
        "risk_medium":  risk_counts.get("Medium", 0),
        "risk_low":     risk_counts.get("Low",    0),
        "duration_s":   total_time,
        "output_csv":   str(output_csv),
    }

    print(f"""
✅  {ok_count} assets → {output_csv}

=================================================================
  Scope           : {scope_label}
  Total processed : {ok_count}
  Errors          : {error_count}
  LLM failures    : {llm_fail_count}
  Risk — High     : {risk_counts.get("High", 0)}
  Risk — Medium   : {risk_counts.get("Medium", 0)}
  Risk — Low      : {risk_counts.get("Low", 0)}
  Total time      : {total_time//60}m{total_time%60:02d}s
=================================================================
""")

    return summary
