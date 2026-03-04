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
    }


def get_dashboard_config(config: dict) -> dict:
    """Extract dashboard configuration."""
    dashboard = config.get("dashboard", {})
    
    return {
        "port": dashboard.get("port", 8501),
        "auto_launch": dashboard.get("auto_launch", True),
    }


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
