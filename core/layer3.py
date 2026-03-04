from datetime import datetime
from pathlib import Path


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

    # ── Age warning ───────────────────────────────────────────────────────
    age_warning   = ""
    yr            = project.get("year_range", [])
    project_start = yr[0] if yr else 1900

    try:
        raw_year     = layer2.get("year") or meta.get("year")
        # Strip Layer 1 mtime annotation (e.g. "2022 (mtime)") before parsing
        raw_year_str = str(raw_year).split()[0] if raw_year else "0"
        y            = int(raw_year_str or 0)
        current_year = datetime.now().year
        if 1900 < y <= current_year:
            age_years = current_year - y
            if y < project_start:
                age_warning = (f"WARNING: dated {y} — predates project start "
                               f"({project_start}), verify relevance")
            elif age_years > 5:
                age_warning = f"NOTICE: {age_years} years old — verify currency"
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
    if "extraction failed" in coverage:   warnings.append("unreadable content")

    review_reasons = critical + warnings

    # ── Review priority (determine if manual review is needed) ────────────
    if critical:
        review_priority = "Urgent"
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
