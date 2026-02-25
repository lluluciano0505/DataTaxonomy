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
        y            = int(raw_year or 0)
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

    # ── Hard flags → force High risk ─────────────────────────────────────
    hard_flags = []
    if confidentiality == "Confidential": hard_flags.append("confidential file")
    if not llm_ok:                        hard_flags.append("LLM classification failed")
    if age_warning.startswith("WARNING"): hard_flags.append("file predates project")

    # ── Soft flags → accumulate ───────────────────────────────────────────
    soft_flags = []
    if governance == "Unknown":           soft_flags.append("source unclear")
    if confidence == "Low":               soft_flags.append("low classification confidence")
    if domain     == "Unknown":           soft_flags.append("domain unidentified")
    if ("no extraction" in coverage or
            "extraction failed" in coverage):
        soft_flags.append("content unreadable — binary or error")

    review_reasons = hard_flags + soft_flags

    # ── Risk level ────────────────────────────────────────────────────────
    if hard_flags:
        risk_level = "High"
    elif len(soft_flags) >= 2:
        risk_level = "High"
    elif len(soft_flags) == 1:
        risk_level = "Medium"
    else:
        risk_level = "Low"

    # ── Recommended action ────────────────────────────────────────────────
    if risk_level == "Low":
        action = "Auto-process"
    else:
        actions = []
        if "confidential file"             in review_reasons: actions.append("Legal / PM review")
        if "LLM classification failed"     in review_reasons: actions.append("Manual classification")
        if "low classification confidence" in review_reasons: actions.append("Manual classification")
        if "file predates project"         in review_reasons: actions.append("Verify relevance with project team")
        if "source unclear"                in review_reasons: actions.append("Verify source with project team")
        if "content unreadable"            in review_reasons: actions.append("Check file integrity")
        seen = set()
        actions = [a for a in actions if not (a in seen or seen.add(a))]
        action  = " + ".join(actions) if actions else "Spot-check recommended"

    return {
        "governance":          governance,
        "confidentiality":     confidentiality,
        "age_warning":         age_warning,
        "risk_level":          risk_level,
        "action":              action,
        "review_reasons":      ", ".join(review_reasons) if review_reasons else "",
        "extraction_coverage": coverage,
    }
