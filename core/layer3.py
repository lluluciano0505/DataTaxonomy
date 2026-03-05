from datetime import datetime
from pathlib import Path


def _calculate_age_warning(file_year: int, project_start: int, project_end: int, current_year: int, min_valid_year: int = 2000) -> str:
    """
    Smart age warning based on project timeline and file age.
    
    Args:
        file_year: Year extracted from file
        project_start: Project start year
        project_end: Project end year
        current_year: Current year
        min_valid_year: Minimum valid year (default 2000, files before this are likely errors)
    
    Returns:
    - "" if no warning needed
    - "NOTICE: ..." for informational warnings
    - "WARNING: ..." for critical warnings
    """
    # Reject years before min_valid_year (likely extraction errors)
    if file_year < min_valid_year or file_year > current_year:
        return ""
    
    age_years = current_year - file_year
    project_duration = project_end - project_start
    
    # Predates project start
    if file_year < project_start:
        years_before = project_start - file_year
        if years_before > 10:
            return f"WARNING: dated {file_year} — {years_before} years before project ({project_start}), verify relevance"
        else:
            return f"NOTICE: dated {file_year} — predates project start ({project_start})"
    
    # Within project duration: usually acceptable
    if file_year <= project_end:
        return ""  # No warning needed
    
    # After project end
    years_after = file_year - project_end
    if years_after > 3:
        return f"NOTICE: dated {file_year} — {years_after} years after project end ({project_end})"
    
    # Within reasonable post-project period (as-built, lessons learned)
    return ""


# ── Public API ────────────────────────────────────────────────────────────
def layer3_trust(
    file_path: Path,
    meta: dict,
    layer2: dict,
    project: dict,
) -> dict:
    """
    Rule-based risk assessment. No LLM call.

    project dict must contain at least:
        { "year_range": [start, end] }
    """
    domain          = layer2.get("domain",          "Unknown")
    governance      = layer2.get("governance",      "Unknown")
    confidentiality = layer2.get("confidentiality", "Standard")
    confidence      = layer2.get("confidence",      "Low")
    llm_ok          = not str(layer2.get("llm", "ok")).startswith("error")
    coverage        = meta.get("extraction_coverage", "")

    # ── Age warning (improved) ────────────────────────────────────────────
    age_warning   = ""
    yr            = project.get("year_range", [])
    project_start = yr[0] if yr else 2000
    project_end   = yr[1] if len(yr) > 1 else datetime.now().year
    current_year  = datetime.now().year

    try:
        raw_year     = layer2.get("year") or meta.get("year")
        # Strip Layer 1 source annotation before parsing (e.g. "2022 (mtime)" → "2022")
        raw_year_str = str(raw_year).split()[0] if raw_year else "0"
        y            = int(raw_year_str or 0)
        
        age_warning = _calculate_age_warning(y, project_start, project_end, current_year)
    except Exception:
        pass

    # ── Critical flags (requires manual review) ──────────────────────────
    critical = []
    if confidentiality == "Confidential": critical.append("confidential")
    if not llm_ok:                        critical.append("llm failed")
    if age_warning.startswith("WARNING"): critical.append("outdated file")

    # ── Warning flags (requires review) ───────────────────────────────────
    warnings = []
    if governance == "Unknown":           warnings.append("unknown source")
    if confidence == "Low":               warnings.append("low confidence")
    if domain == "Unknown":               warnings.append("unknown domain")
    
    # Only flag extraction failures for formats that should be readable
    # Don't penalize binary CAD formats (DWG, RVT, etc.)
    if "extraction failed" in coverage:
        file_ext = str(file_path.suffix).lower()
        if file_ext not in {".dwg", ".rvt", ".nwd", ".rfa", ".rte"}:
            warnings.append("unreadable content")

    review_reasons = critical + warnings

    # ── Review priority (determine if manual review is needed) ────────────
    if critical:
        review_priority = "Critical"
    elif len(warnings) >= 2:
        review_priority = "High"
    elif warnings:
        review_priority = "Medium"
    else:
        review_priority = "Low"

    # ── Recommended action ────────────────────────────────────────────────
    if review_priority == "Low":
        action = "Auto-process"
    else:
        actions = []
        if "confidential" in review_reasons:    actions.append("Legal review")
        if "llm failed" in review_reasons:      actions.append("Manual classification")
        if "low confidence" in review_reasons:  actions.append("Manual review")
        if "outdated file" in review_reasons:   actions.append("Verify relevance")
        if "unknown source" in review_reasons:  actions.append("Verify source")
        if "unreadable content" in review_reasons: actions.append("Check file")
        actions = list(dict.fromkeys(actions))  # deduplicate
        action = " → ".join(actions) if actions else "Spot-check"

    return {
        "governance":          governance,
        "confidentiality":     confidentiality,
        "age_warning":         age_warning,
        "review_priority":     review_priority,
        "action":              action,
        "review_reasons":      ", ".join(review_reasons) if review_reasons else "",
        "extraction_coverage": coverage,
    }
