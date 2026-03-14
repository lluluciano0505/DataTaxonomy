"""config.py — Load configuration from YAML or environment variables."""

import os
from pathlib import Path
from typing import Any, Optional
import yaml


def load_config(config_path: str = "config.yaml") -> dict:
    """Load configuration from YAML file."""
    cfg_file = Path(config_path)
    
    if not cfg_file.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {config_path}\n"
            f"Please create {config_path} in the project root.\n"
            f"See config.yaml.example for template."
        )
    
    try:
        with open(cfg_file, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ValueError(f"Error parsing {config_path}: {e}")
    
    return config or {}


def expand_path(path_str: str) -> Path:
    """Expand ~ and convert to absolute Path."""
    return Path(path_str).expanduser().absolute()


def get_project_config(config: dict) -> dict:
    """Extract and validate project configuration."""
    project = config.get("project", {})
    
    required = ["name", "location", "year_range"]
    for key in required:
        if key not in project:
            raise ValueError(f"Missing required project field: {key}")
    
    return project


def get_paths_config(config: dict) -> dict:
    """Extract and validate paths configuration."""
    paths = config.get("paths", {})
    
    input_dir = expand_path(paths.get("input_dir", "~/Desktop"))
    output_csv = Path(paths.get("output_csv", "output.csv"))
    
    return {
        "input_dir": input_dir,
        "output_csv": output_csv,
    }


def get_processing_config(config: dict) -> dict:
    """Extract processing configuration."""
    proc = config.get("processing", {})
    
    sample_n = proc.get("sample_n", None)  # None = all files
    model = proc.get("model", "google/gemini-2.0-flash-001")
    
    return {
        "sample_n": sample_n,
        "model": model,
        "parallel_workers": int(proc.get("parallel_workers", 1)),
        "api_timeout": int(proc.get("api_timeout", 30)),
    }


def get_dashboard_config(config: dict) -> dict:
    """Extract dashboard configuration."""
    dashboard = config.get("dashboard", {})
    
    return {
        "port": dashboard.get("port", 8501),
        "auto_launch": dashboard.get("auto_launch", True),
    }


# ── Taxonomy defaults (fallback when taxonomy.yaml not present) ───────────
_TAXONOMY_DEFAULTS: dict = {
    "domains": [
        {"name": "Landscape & Public Realm",  "description": "landscape design, planting plans, hardscape, open space, parks, streetscape, urban furniture"},
        {"name": "Urban Planning & Massing",   "description": "masterplan drawings, land use, zoning, urban morphology, massing studies, plot ratios, phasing plans"},
        {"name": "Architecture & Buildings",   "description": "building design, floor plans, sections, elevations, facades, interior layouts, structural drawings"},
        {"name": "Environment & Climate",      "description": "ecology, biodiversity, hydrology, wind, noise, sustainability assessments"},
        {"name": "Mobility & Transport",       "description": "roads, transit, parking, pedestrian/cycling networks, traffic analysis"},
        {"name": "Administrative & Legal",     "description": "contracts, permits, legal agreements, regulatory submissions, formal approvals, legal correspondence"},
        {"name": "Project Management",         "description": "schedules, budgets, meeting notes, RFIs, transmittals, internal coordination, fee tracking"},
        {"name": "Reference & Research",       "description": "precedents, standards, regulations, academic sources, background data"},
        {"name": "Unknown",                    "description": "cannot determine from available information"},
    ],
    "scales": [
        {"name": "Object / Parcel",         "description": "single building, plot, element, or detail"},
        {"name": "Neighborhood / District", "description": "urban block, district, or zone"},
        {"name": "City / Municipal",        "description": "city-wide or full masterplan scope"},
        {"name": "Regional / National",     "description": "regional, national, or cross-boundary"},
        {"name": "Non-spatial",             "description": "no meaningful geographic scope"},
    ],
    "lifecycle_stages": [
        {"name": "Brief / Concept",        "description": "early ideas, vision docs, RFPs, feasibility"},
        {"name": "Schematic Design",       "description": "SD phase drawings, reports, presentations"},
        {"name": "Design Development",     "description": "DD phase, developed drawings and specs"},
        {"name": "Construction Documents", "description": "CD phase, permit sets, tender packages, 100% submissions"},
        {"name": "As-Built / Completed",   "description": "final built condition, completion records"},
        {"name": "Reference / Archive",    "description": "background research, precedents, standards, regulations"},
        {"name": "Unknown",                "description": "cannot determine from available information"},
    ],
    "confidentiality_levels": [
        {"name": "Confidential", "description": "contracts, fee proposals, budgets, cost plans, legal agreements, NDAs, invoices, financial models, HR files"},
        {"name": "Sensitive",    "description": "internal drafts, WIP coordination files, meeting minutes, preliminary studies not yet issued externally"},
        {"name": "Standard",     "description": "issued drawings, public reports, technical specs, reference data, regulatory documents"},
    ],
}


def load_taxonomy(taxonomy_path: str = "taxonomy.yaml") -> dict:
    """Load classification taxonomy from YAML. Falls back to built-in defaults if file not found."""
    tax_file = Path(taxonomy_path)
    if not tax_file.exists():
        return _TAXONOMY_DEFAULTS.copy()
    try:
        with open(tax_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if data else _TAXONOMY_DEFAULTS.copy()
    except yaml.YAMLError:
        return _TAXONOMY_DEFAULTS.copy()


def save_taxonomy(taxonomy: dict, taxonomy_path: str = "taxonomy.yaml") -> None:
    """Save classification taxonomy to YAML file."""
    with open(taxonomy_path, "w", encoding="utf-8") as f:
        yaml.dump(taxonomy, f, allow_unicode=True, sort_keys=False, default_flow_style=False)


def validate_input_path(input_dir: Path) -> bool:
    """Check if input directory exists and has files."""
    if not input_dir.exists():
        print(f"⚠️  Input directory not found: {input_dir}")
        return False
    
    files = list(input_dir.glob("*"))
    if not files:
        print(f"⚠️  Input directory is empty: {input_dir}")
        return False
    
    return True
