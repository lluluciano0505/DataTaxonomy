"""
Layer 2 — LLM Domain Classification
=====================================
Receives the Layer 1 metadata dict, calls an OpenRouter-compatible LLM, and returns
a classification dict with domain, scale, lifecycle, asset_type, governance,
confidentiality, confidence, short_summary, and _reasoning.

Key design decisions
────────────────────
• path_segments are injected as a structured folder chain, NOT mixed with content.
• filename_signals (discipline_code, status_tag, version, drawing_number) are served
  as pre-parsed facts so the LLM doesn't have to parse raw filenames itself.
• A lifecycle_hint is pre-computed from status_tag before the LLM call, reducing
  ambiguity on the most common error class.
• chain-of-thought via _reasoning field forces the model to reason before classifying.
• content_sample cap raised from 600 → 1400 chars (Layer 1 provides up to 2400).
• Retry once at temperature 0.3 on JSON parse failure.
"""

import json
import re
from pathlib import Path
from openai import OpenAI

# ── Data detection config (moved from Layer 1) ──────────────────────────
_FORMAT_DATA_SCORE = {
  ".csv":     5,   ".shp":     5,   ".geojson": 5,
  ".kml":     5,   ".gpkg":    5,
    ".xlsx":    4,   ".xls":     4,   ".json":    3,
  ".dwg":    -4,   ".rvt":    -4,   ".nwd":    -4,   ".dwf":    -3,
  ".ifc":    -1,
  ".mp4":    -4,   ".mov":    -4,
  ".jpg":    -3,   ".jpeg":   -3,   ".png":    -3,
  ".tiff":   -3,   ".tif":    -3,
    ".pdf":     0,   ".pptx":   -1,
    ".docx":    1,   ".doc":    0,
  ".eml":    -2,   ".msg":    -2,
}


def _score_content_structure(content: str) -> int:
  if not content or len(content.strip()) < 40:
    return 0

  lines = [l for l in content.splitlines() if l.strip()]
  if len(lines) < 2:
    return 0

  score = 0

  tokens = re.split(r"[\s,|\t;/]+", content)
  tokens = [t for t in tokens if t]
  if tokens:
    numeric = sum(1 for t in tokens if re.fullmatch(r"-?\d+([.,]\d+)?", t))
    num_ratio = numeric / len(tokens)
    if   num_ratio > 0.35:  score += 3
    elif num_ratio > 0.15:  score += 1
    elif num_ratio < 0.03:  score -= 1

  # ── JSON / key:value / XML signals (semi-structured records) ──────────
  json_kv_hits = len(re.findall(r'"\s*:\s*|\b\w+\s*:\s*[^\n]{1,40}', content))
  if json_kv_hits >= 6:
    score += 3
  elif json_kv_hits >= 3:
    score += 1

  xml_tags = len(re.findall(r"<\/?[A-Za-z_\-:]+\b", content))
  if xml_tags >= 8:
    score += 2
  elif xml_tags >= 3:
    score += 1

  lines = [l for l in content.splitlines() if l.strip()]
  kv_lines = sum(1 for l in lines if re.search(r"\b\w[\w\-]*\s*[:=]\s*[^\n]{1,80}", l))
  if len(lines) >= 5 and (kv_lines / len(lines)) > 0.4:
    score += 2

  delimiters = re.findall(r"[,|\t;]", content)
  delim_per_line = len(delimiters) / len(lines)
  if   delim_per_line > 4:   score += 3
  elif delim_per_line > 1.5: score += 1
  elif delim_per_line < 0.3: score -= 1

  if delim_per_line > 1.0 and len(lines) >= 3:
    lengths  = [len(l.split()) for l in lines]
    mean_len = sum(lengths) / len(lengths)
    if mean_len > 0:
      variance = sum((x - mean_len) ** 2 for x in lengths) / len(lengths)
      cv       = (variance ** 0.5) / mean_len
      if   cv < 0.3:  score += 2
      elif cv < 0.6:  score += 1

  first     = lines[0]
  cols_first = re.split(r"[,|\t;]", first)
  if len(cols_first) >= 3:
    avg_col_len = sum(len(c.strip()) for c in cols_first) / len(cols_first)
    if avg_col_len < 30:
      score += 2
      if len(lines) > 1:
        cols_second = re.split(r"[,|\t;]", lines[1])
        if len(cols_second) == len(cols_first):
          score += 1

  # ── Table markers from extraction helpers (Layer 1 may include 'Columns:' etc.)
  if re.search(r"\bColumns:\b|\bSheets:\b|\bColumns\b|\bFeatures\b", content):
    score += 2

  return score


def _is_data_hint(file_path: Path, content: str) -> str:
  ext = file_path.suffix.lower()
  score = _FORMAT_DATA_SCORE.get(ext, 0)
  if score >= 5:
    return "Likely"

  if re.search(r"\b[A-Za-z]{1,4}[.\-]\d{3,5}\b", file_path.stem):
    score -= 2

  if content and ext not in {
    ".dwg", ".rvt", ".nwd", ".dwf",
    ".mp4", ".mov", ".jpg", ".jpeg", ".png", ".tiff", ".tif",
    ".msg",
  }:
    score += _score_content_structure(content)

  if   score >= 4:  return "Likely"
  elif score >= 1:  return "Possible"
  else:             return "Unlikely"


# ── Lifecycle hint — content structure analysis ───────────────────────────
def _lifecycle_hint(meta: dict) -> str | None:
    """
    Infer lifecycle stage from structural signals in the content sample and
    filename token shapes.  No enumeration of status-code abbreviations —
    those are English-centric and naming-convention-specific.

    Instead we look for signals that are structurally distinct regardless of
    language: approval stamps (date + signature block patterns), clause
    numbering depth, revision frequency, and percentage-of-completion markers.

    The LLM sees the raw code_tokens (ARCH, IFC, WIP, …) directly and can
    interpret their meaning; our job here is only to detect coarse lifecycle
    position from objective structural features.
    """
    content = (meta.get("content_sample") or "")
    signals = meta.get("filename_signals") or {}

    # ── Drawing number → almost always a formal issued document ──────────
    # Pattern: letter-code + separator + 3–5 digits (A-001, SK-024, C.003)
    # Language-agnostic: this is a structural drawing reference format
    if signals.get("drawing_number"):
        # Has version/revision too → still in development
        if signals.get("version"):
            return "Design Development"
        # No revision marker on an issued drawing → likely CD or later
        return "Construction Documents"

    if not content:
        return None

    # ── Completion / handover: late-stage structural markers ─────────────
    # Signature + date fields together = formal document execution
    sig_blocks  = len(re.findall(r"_{5,}|\.{5,}", content))
    date_fields = len(re.findall(r"Date\s*[:/]?\s*_{3,}|\bDate\b.{0,20}\d{1,2}[/\-\.]\d{1,2}", content, re.IGNORECASE))
    if sig_blocks >= 2 and date_fields >= 1:
        return "Construction Documents"   # executed / issued document

    # ── As-built: specific text patterns that cross language boundaries ───
    # These phrases appear on drawings globally (often in English even on
    # Arabic/French projects because they are international AEC conventions)
    if re.search(r"\bAS[- ]?BUILT\b|\bRECORD DRAWING\b|\bHANDOVER\b", content, re.IGNORECASE):
        return "As-Built / Completed"

    # ── Revision table: structured rows with version + date pattern ───────
    # Matches:  "Rev 1  12/01/2023"  or  "1  12/01/2023"  or  "A  01-03-2023"
    # Using date-shape (N/N or N-N) not language keywords.
    rev_entries = len(re.findall(
        r"(?:^|\n)\s*(?:\w{1,5}\s+)?\d+\s+\d{1,2}[/\-.]\d{1,2}",
        content,
    ))
    if rev_entries >= 3:
        return "Design Development"

    # ── Feasibility / concept: questions + labelled options ──────────────
    # Multiple question marks OR labelled alternatives (Option A / Alternative 1)
    # are structural fingerprints of early-phase exploration documents.
    question_marks = content.count("?")
    option_markers = len(re.findall(r"\bOption\s+[A-Z\d]\b|\bAlternative\s+\d\b", content, re.IGNORECASE))
    if question_marks >= 3 or option_markers >= 2:
        return "Brief / Concept"

    return None


# ── Asset type hint — format + is_data_hint only ─────────────────────────
_HARD_DATA_FORMATS = {"CSV", "XLSX", "XLS", "JSON", "SHP", "GEOJSON", "KML", "GPKG"}

def _asset_type_hint(meta: dict) -> str | None:
    """
    Pre-compute asset_type from format + Layer 1 is_data_hint.
    No filename/folder keyword matching — is_data_hint already encoded that
    via content-structure analysis.  This function only translates format
    facts and the pre-computed data hint into an asset_type suggestion.
    """
    fmt  = (meta.get("format") or "").upper()
    hint = meta.get("is_data_hint", "Unlikely")

    if fmt in _HARD_DATA_FORMATS:
        return "Data"
    if fmt in {"DWG", "DXF", "RVT", "NWD"}:
        return "Drawing"
    if fmt == "IFC":
        return "Drawing"   # default; content override handled by LLM
    if hint == "Likely":
        return "Data"
    return None


# ── Confidentiality hint — content structure analysis ─────────────────────
def _confidentiality_hint(meta: dict) -> str | None:
    """
    Detect confidentiality level from content structure and metadata patterns.
    No keyword lists — those are English-only and fail on Arabic/French/other
    language projects or when clients use internal terminology.

    What we measure (all language-agnostic structural signals):

    currency_density   — international currency symbols + codes ($ £ € ¥ SAR
                         AED QAR USD EUR GBP) followed by numbers.  Presence
                         of 3+ hits strongly suggests financial content.

    clause_depth       — numbered paragraph structure like 1.1, 1.1.1, or
                         Article/Clause/Section N.  Deep clause nesting is
                         the structural fingerprint of legal agreements.

    signature_blocks   — runs of underscores (______) or dots (......) used
                         as signature/date fill-in lines.  Formal execution
                         markers.

    fee_percentage     — numbers followed by % in quantity (fee proposals,
                         cost plans, and budget sheets are full of these).

    revision_markers   — Rev/v + number in content body (not just filename).
                         Multiple revision entries → internal working document.

    draft_watermark    — the word DRAFT or NOT FOR ISSUE appearing in all-caps
                         blocks (common watermark pattern regardless of language).
    """
    content = (meta.get("content_sample") or "")
    if not content:
        return None

    conf_score = 0
    sens_score = 0

    # ── Currency amounts ──────────────────────────────────────────────────
    currency_hits = len(re.findall(
        r"[\$£€¥]\s?\d[\d,\.]*"                          # symbol-prefix
        r"|\b\d[\d,\.]+\s*(?:SAR|AED|QAR|USD|EUR|GBP)\b" # number-suffix code
        r"|\b(?:SAR|AED|QAR|USD|EUR|GBP)\s?\d[\d,\.]+",   # code-prefix
        content, re.IGNORECASE,
    ))
    if   currency_hits >= 3:  conf_score += 3
    elif currency_hits >= 2:  conf_score += 2
    elif currency_hits >= 1:  conf_score += 1

    # ── Legal clause numbering depth ──────────────────────────────────────
    # 3-level numbering (1.1.1) is the structural fingerprint of legal/contract
    # documents — almost never appears in technical drawings or reports.
    # Even a single instance is meaningful; multiple instances are conclusive.
    deep_clauses = len(re.findall(r"^\s*\d+\.\d+\.\d+", content, re.MULTILINE))
    flat_clauses = len(re.findall(r"^\s*\d+\.\d+\s", content, re.MULTILINE))
    if   deep_clauses >= 2:   conf_score += 3   # very strong legal signal
    elif deep_clauses >= 1:   conf_score += 2   # strong — rarely appears elsewhere
    elif flat_clauses >= 5:   conf_score += 2
    elif flat_clauses >= 2:   conf_score += 1

    # ── Signature / date fill blocks ──────────────────────────────────────
    sig_blocks = len(re.findall(r"_{5,}|\.{8,}", content))
    if   sig_blocks >= 3:     conf_score += 2
    elif sig_blocks >= 1:     conf_score += 1

    # ── Percentage values (fee structures, cost plans) ────────────────────
    pct_hits = len(re.findall(r"\d+(?:\.\d+)?\s*%", content))
    if   pct_hits >= 5:       conf_score += 2
    elif pct_hits >= 2:       conf_score += 1

    # ── Revision markers in content body (internal WIP) ───────────────────
    rev_in_content = len(re.findall(r"\bRev(?:ision)?\s*[A-Z\d]|\bv\d+\b", content, re.IGNORECASE))
    if   rev_in_content >= 3: sens_score += 2
    elif rev_in_content >= 1: sens_score += 1

    # ── Draft watermark (structural: all-caps block word) ─────────────────
    if re.search(r"\bDRAFT\b|\bNOT FOR ISSUE\b|\bINTERNAL USE\b", content, re.IGNORECASE):
        sens_score += 2

    # ── Score → label ─────────────────────────────────────────────────────
    if   conf_score >= 4:     return "Confidential"
    elif conf_score >= 2:     return "Sensitive"
    elif sens_score >= 2:     return "Sensitive"
    return None



def _format_path_segments(meta: dict, input_path: Path, file_path: Path) -> str:
    """
    Return a human-readable folder chain string.

    Prefers the Layer 1 path_segments list (which already strips noise like
    'Users', 'Downloads' etc.) and falls back to computing from the relative
    path if the field is absent (backwards compat with old Layer 1 output).
    """
    segments = meta.get("path_segments")
    if segments:
        return " / ".join(segments)

    # Fallback: compute from relative path
    try:
        rel = file_path.parent.relative_to(input_path)
        parts = [p for p in rel.parts if p not in (".", "")]
        return " / ".join(parts) if parts else meta.get("folder", "")
    except ValueError:
        return meta.get("folder", "")


def _format_filename_signals(meta: dict) -> str:
    """
    Render filename_signals as a compact block for the prompt.
    Presents raw structural tokens so the LLM can interpret meaning
    without pre-baked keyword mappings.
    """
    signals = meta.get("filename_signals") or {}
    if not signals:
        return "  (not available — old Layer 1 output)"

    lines = []

    # Raw stem first — LLM reads the full name
    if signals.get("raw_stem"):
        lines.append(f"  Full stem:       {signals['raw_stem']}")

    # Code tokens: short ALL-CAPS segments — LLM interprets meaning
    codes = signals.get("code_tokens")
    if codes:
        lines.append(f"  Code tokens:     {' | '.join(codes)}"
                     "  ← discipline / status / zone codes — LLM interprets")

    if signals.get("drawing_number"):
        lines.append(f"  Drawing ref:     {signals['drawing_number']}"
                     "  ← strong signal: this is a drawing file")
    if signals.get("version"):
        lines.append(f"  Version:         {signals['version']}")
    if signals.get("numeric_tokens"):
        lines.append(f"  Numeric tokens:  {' | '.join(signals['numeric_tokens'])}"
                     "  ← zone / phase / sequence IDs")
    if signals.get("has_date_in_name"):
        lines.append("  Date in name:    yes")
    if signals.get("token_count") is not None:
        lines.append(f"  Token count:     {signals['token_count']}"
                     "  (≥5 suggests structured naming convention)")

    return "\n".join(lines) if lines else "  (no structural signals detected)"


# ── Prompt ────────────────────────────────────────────────────────────────
LAYER2_PROMPT = """\
You are an urban design data classifier working on a large-scale city project.
Your task: analyse the structured file metadata below and classify the file.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PROJECT CONTEXT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{project_context}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FILE IDENTITY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Filename:    {filename}
  Format:      {format}
  Size:        {size_kb} KB  ({size_category})
  Pages:       {page_count}
  Year:        {year}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FOLDER CONTEXT  (project root → parent folder)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {folder_chain}

  The folder chain is your strongest signal for both DOMAIN and LIFECYCLE.
  Read every segment — each level can encode discipline, phase, and date.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FILENAME SIGNALS  (structural token extraction — you interpret meaning)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{filename_signals_block}

  Code tokens are short ALL-CAPS segments from the filename.  Interpret them
  using your AEC domain knowledge (ARCH → Architecture, MEP → M/E/P, IFC →
  Issued For Construction, WIP → Work In Progress, etc.).  A drawing_ref
  confirms this is a drawing file regardless of extension.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LIFECYCLE HINT  (pre-computed from content structure)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {lifecycle_hint_str}

  This hint is derived from structural signals in the content and filename
  (signature blocks + date fields, drawing reference patterns, revision tables,
  as-built markers) — not from a keyword list.  It is a strong signal when
  present.  Override it ONLY if the folder path or content clearly contradicts it.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ASSET TYPE HINT  (pre-computed from format + Layer 1 data signals)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {asset_type_hint_str}

  This hint was computed from file format and keyword analysis BEFORE this call.
  Treat it as a strong default for asset_type.
  Override ONLY if the content sample clearly shows it is wrong.
  Raw Layer 1 data signal: {is_data_hint}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONFIDENTIALITY HINT  (pre-computed from content structure)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {confidentiality_hint_str}

  This hint is derived from structural signals in the extracted content:
  currency amounts ($ £ € SAR AED…), legal clause numbering depth (1.1.1…),
  signature/date fill blocks (______), percentage values, and draft watermarks.
  No filename keywords are used.  Override only if content clearly contradicts.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONTENT SAMPLE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Information type hint: {information_type}

{content_sample}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CLASSIFICATION INSTRUCTIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Step 1: Write a brief reasoning chain in _reasoning (2–4 sentences max).
  Identify which signals are present and which fields they support.
  If signals conflict, explain how you resolved it.
  This is the ONLY free-form text you return.

Step 2: Fill every classification field using the rules below.

─── DOMAIN ───────────────────────────────────────────────────────────────
Pick one:
  Administrative & Legal     — contracts, permits, legal agreements, regulatory
                               submissions, formal approvals, legal correspondence
  Architecture & Buildings   — building design, floor plans, sections, elevations,
                               facades, interior layouts, structural drawings
  Landscape & Public Realm   — landscape design, planting plans, hardscape, open
                               space, parks, streetscape, urban furniture
  Urban Planning & Massing   — masterplan drawings, land use, zoning, urban
                               morphology, massing studies, plot ratios, phasing plans
  Mobility & Transport       — roads, transit, parking, pedestrian/cycling networks
  Environment & Climate      — ecology, hydrology, wind, noise, sustainability
  Social & Demographics      — population, housing needs, community data
  Utilities & Infrastructure — water, energy, waste, telecoms, drainage systems
  Project Management         — schedules, budgets, meeting notes, RFIs, transmittals,
                               internal coordination, fee tracking
  Reference & Research       — precedents, standards, regulations, academic sources
  Unknown                    — cannot determine from available information

DOMAIN DECISION RULES (check in order):
  1. If filename_signals.discipline_code is set, use it as your primary domain
     signal — it is more reliable than folder names alone:
       Architecture / ARCH → Architecture & Buildings
       Structure / STRUC / STR → Architecture & Buildings (structural sub-domain)
       Landscape / LAND / LS → Landscape & Public Realm
       Civil / CVL → Mobility & Transport or Utilities depending on content
       Planning / PLN → Urban Planning & Massing
       MEP / MECH / ELEC / PLMB → Utilities & Infrastructure
       GIS → assign by content; default to Urban Planning & Massing
       PM / PMO → Project Management
       Survey / SURV → Reference & Research
  2. Folder prefix tiebreakers:
       "Architecture/", "A-"  → Architecture & Buildings
       "Landscape/", "L-"     → Landscape & Public Realm
       "Masterplan/", "MP-", "Urban/" → Urban Planning & Massing
       "Admin/", "Legal/", "Contracts/" → Administrative & Legal
  3. Site plans showing building footprints, land use, or plot boundaries
     → Urban Planning & Massing (NOT Architecture)
  4. Detailed floor plans, sections, elevations, facade, interior
     → Architecture & Buildings
  5. If a drawing covers multiple disciplines, pick by the primary subject;
     use discipline_code or folder path as tiebreaker
  6. .ifc / .rvt → assign by discipline_code or folder path, not format alone
  7. .geojson / .shp / .kml → use folder path to assign domain
  8. Legal/binding documents (regardless of format) → Administrative & Legal
  9. Process/coordination files → Project Management

─── SCALE ────────────────────────────────────────────────────────────────
Pick one:
  Object / Parcel            — single building, plot, element, or detail
  Neighborhood / District    — urban block, district, or zone
  City / Municipal           — city-wide or full masterplan scope
  Regional / National        — regional, national, or cross-boundary
  Non-spatial                — no meaningful geographic scope

SCALE RULES:
  - "masterplan" anywhere in folder chain → City / Municipal
  - "detail", "element", title block drawings → Object / Parcel
  - "district", "zone", "block" → Neighborhood / District
  - Contracts, emails, reports, schedules → Non-spatial
  - is_data_hint=Likely with no clear spatial scope → Non-spatial

─── INFORMATION_TYPE ─────────────────────────────────────────────────────
Pick one:
  Schematic / Technical      — drawings, diagrams, CAD, BIM
  Quantitative / Tabular     — data tables, spreadsheets, statistics
  Narrative / Textual        — reports, descriptions, correspondence
  Spatial / Cartographic     — maps, GIS, geographic datasets
  Visual / Media             — photos, renders, presentations, linked assets
  Archive                    — compressed or bundled files
  Unknown

INFORMATION_TYPE RULES:
  - Only override the Layer 1 hint if you are confident it is wrong
  - Folder names "Renders", "Links", "Images" → Visual / Media
  - is_data_hint=Likely + tabular format → Quantitative / Tabular
  - is_data_hint=Likely + spatial format → Spatial / Cartographic

─── LIFECYCLE ────────────────────────────────────────────────────────────
Pick one:
  Brief / Concept            — early ideas, vision docs, RFPs, feasibility
  Schematic Design           — SD phase drawings, reports, presentations
  Design Development         — DD phase, developed drawings and specs
  Construction Documents     — CD phase, permit sets, tender packages, 100% submissions
  As-Built / Completed       — final built condition, completion records
  Reference / Archive        — background research, precedents, standards, regulations
  Unknown                    — cannot determine from available information

LIFECYCLE RULES (apply in order):
  1. If the LIFECYCLE HINT above is set, use it as your default answer.
     Override only if the folder chain strongly contradicts it.
  2. Folder path keywords (higher priority than content):
       "100%", "final", "issued for construction", "IFC", "AFC" → Construction Documents
       "schematic", "SD", "concept" → Schematic Design
       "DD", "design development", "developed", "render" → Design Development
       "as-built", "as built", "record", "completion" → As-Built / Completed
       "brief", "feasibility", "concept" → Brief / Concept
  3. Content keywords:
       "permit", "approval", "tender", "issued for" → Construction Documents
       "feasibility", "option study", "vision" → Brief / Concept
  4. Research papers, regulations, standards, background datasets
     → Reference / Archive
  5. GIS layers without a clear project phase → Reference / Archive
  6. If the year (from filename or content) is significantly earlier than the
     project start year, lean toward Reference / Archive

─── GOVERNANCE ───────────────────────────────────────────────────────────
Pick one:
  Official    — produced by a government body, municipality, or regulatory authority
  Internal    — produced by the project team (lead firm or any consultant)
  External    — produced by a third party outside the project team
  Unknown

GOVERNANCE SIGNALS:
  Official:  authority/ministry names, approval stamps, official letterheads,
             "shall", "is required to", "Royal Decree", permit IDs, planning refs
  Internal:  project drawing code convention, firm abbreviations, WIP/draft/revision
             markers, meeting minutes, transmittal formats, internal templates
  External:  stock imagery, academic papers, census data, satellite imagery,
             commercial GIS layers, third-party technical standards
  Rule: a document may cite official sources but still be Internal.
        Unknown only when zero signals are available.

─── CONFIDENTIALITY ──────────────────────────────────────────────────────
Pick one:
  Confidential  — contracts, fee proposals, budgets, cost plans, legal agreements,
                  NDAs, LOAs, LOIs, MoUs, invoices, payment records, financial models,
                  HR / personnel files, private correspondence, bid prices
  Sensitive     — internal draft reports, WIP coordination files, meeting minutes,
                  RFIs, transmittals, internal memos, staff-facing documents,
                  preliminary / pre-design studies not yet issued externally
  Standard      — issued drawings, public reports, technical specs, reference data,
                  regulatory documents, presentations for client/authority review

CONFIDENTIALITY RULES (apply in order):
  1. If CONFIDENTIALITY HINT above is 'Confidential' or 'Sensitive', use it.
     Override only if the content sample is clearly a public technical document.
  2. Content signals → Confidential:
       Visible fee amounts, cost breakdowns, budget tables, contract clauses,
       "confidential", "private", "proprietary", legal party names + signatures
  3. Content signals → Sensitive:
       "internal use only", "draft", "not for issue", "WIP", action items,
       attendee lists, revision comments not yet resolved
  4. Default to Standard for issued drawings, specs, public-facing reports.
  5. Do NOT default everything to Standard — if the hint says Confidential,
     trust it unless content proves otherwise.

─── ASSET_TYPE ───────────────────────────────────────────────────────────
Pick one:
  Data         — structured/semi-structured datasets: spreadsheets with measurement
                 columns, GIS layers, survey tables, sensor outputs, inventories,
                 BIM property sets, census extracts
  Document     — narrative or formatted content: reports, specs, contracts,
                 correspondence, standards, presentations, PDFs
  Drawing      — geometric/spatial representations: CAD, BIM models, floor plans,
                 sections, elevations, site plans
  Media        — non-geometric visual content: photos, renders, videos, infographics
  Archive      — bundled or compressed collections of other assets
  Unknown

ASSET_TYPE RULES (apply in order — first match wins):
  1. If ASSET TYPE HINT above is set, USE IT as your answer for asset_type.
     Override only if the content sample clearly contradicts it.
     Example: hint=Data but content shows it is a narrative report → Document.
  2. Format hard rules (no override):
       .csv / .xlsx / .xls / .json / .shp / .geojson / .kml / .gpkg → Data
       .dwg / .dxf / .rvt                                            → Drawing
       .jpg / .jpeg / .png / .tiff / .mp4 / .mov                     → Media
       .zip / .7z / .rar                                              → Archive
       .pptx                                                           → Document
  3. .ifc → Drawing by default; Data only if content shows it is a property-set
     or data-export file (entity counts dominated by IFCPROPERTYSET / IFCRELDEFINES)
  4. .pdf rules:
       Content shows column headers, data rows, quantities, schedules → Data
       Content shows narrative text, headings, body paragraphs        → Document
       Content shows vector diagram descriptions, no text             → Drawing
  5. Ambiguity test: "Could this file be imported into a database or GIS as-is?"
       Yes → Data.  No → Document or Drawing based on format.

─── YEAR, CONFIDENCE, SHORT_SUMMARY ──────────────────────────────────────
YEAR:
  - Use pre-extracted year if not null
  - Ignore years marked "(mtime)" unless no other year is available (mtime = OS
    modification date, not document date — less reliable)
  - Extract from folder chain if filename/content year is null (e.g. "2022_02_06")
  - Return integer YYYY or null

CONFIDENCE:
  High   — 3+ signals present and consistent, no contradictions
  Medium — 1–2 signals clear, rest generic or mildly inconsistent
  Low    — generic filename AND generic folder, or signals clearly contradict

SHORT_SUMMARY:
  One sentence, max 15 words, describing the file's likely purpose.
  Be specific: name the discipline and phase if known.
  Good:  "Architecture floor plan at Construction Documents stage for Zone B."
  Bad:   "This file contains architectural information."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
RESPONSE FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Return ONLY this JSON object, nothing else:

{{
  "_reasoning":       "<2-4 sentence reasoning chain>",
  "domain":           "<value>",
  "scale":            "<value>",
  "information_type": "<value>",
  "lifecycle":        "<value>",
  "governance":       "<value>",
  "confidentiality":  "<value>",
  "asset_type":       "<value>",
  "year":             <YYYY or null>,
  "confidence":       "<High|Medium|Low>",
  "short_summary":    "<sentence>"
}}
"""


# ── Public API ────────────────────────────────────────────────────────────
def layer2_domain(
    meta: dict,
    client: OpenAI,
    model: str,
    input_path: Path,
    project_context: str,
    temperature: float = 0,
) -> dict:
    """
    Classify a file using the LLM.

    Parameters are passed explicitly (no globals) so this function
    works cleanly when called from FastAPI / Celery workers.

    New in v2
    ─────────
    • Uses path_segments, filename_signals, size_category, page_count from Layer 1 v2.
    • Pre-computes a lifecycle_hint from filename_signals.status_tag.
    • content_sample cap raised from 600 → 1400 chars.
    • Retries once at temperature=0.3 on JSON parse failure.
    • Returns _reasoning field from the LLM for debugging.
    • Backwards-compatible: works with old Layer 1 output (missing new fields).
    """
    file_path = Path(meta["file_path"])

    # ── Build structured context blocks ──────────────────────────────────
    folder_chain           = _format_path_segments(meta, input_path, file_path)
    filename_signals_block = _format_filename_signals(meta)

    # Lifecycle hint
    lc_hint            = _lifecycle_hint(meta)
    lifecycle_hint_str = (
        f"Suggested: {lc_hint}  (from status tag '{(meta.get('filename_signals') or {}).get('status_tag', '')}')"
        if lc_hint else
        "No status-tag hint available — infer from folder chain and content."
    )

    # Compute data hint here (moved from Layer 1)
    try:
      meta["is_data_hint"] = _is_data_hint(file_path, meta.get("content_sample") or "")
    except Exception:
      meta["is_data_hint"] = "Unlikely"

    # Asset type hint — pre-computed from format + is_data_hint
    at_hint            = _asset_type_hint(meta)
    asset_type_hint_str = (
        f"Suggested: {at_hint}  (from format '{meta.get('format','')}' + data signal '{meta.get('is_data_hint','')}')"
        if at_hint else
        "No strong signal — infer from content sample and format."
    )

    # Confidentiality hint — pre-computed from filename + folder keywords
    conf_hint               = _confidentiality_hint(meta)
    confidentiality_hint_str = (
        f"Suggested: {conf_hint}  (keyword matched in filename or folder path)"
        if conf_hint else
        "No confidentiality keywords detected — default to Standard unless content shows otherwise."
    )

    # ── Year: strip "(mtime)" suffix for the prompt display ──────────────
    year_raw  = meta.get("year") or "null"
    year_disp = str(year_raw).replace(" (mtime)", " ⚠ OS date only") if year_raw else "null"

    # ── Content sample: raise cap to 1400 chars ───────────────────────────
    content_sample = (meta.get("content_sample") or "")[:1400]
    # Indent each line for visual separation in the prompt block
    content_indented = "\n".join("  " + line for line in content_sample.splitlines()) if content_sample else "  (no content extractable)"

    prompt = LAYER2_PROMPT.format(
        project_context          = project_context,
        filename                 = meta["filename"],
        format                   = meta["format"],
        size_kb                  = meta.get("size_kb", "?"),
        size_category            = meta.get("size_category", "unknown"),
        page_count               = meta.get("page_count") or "n/a",
        year                     = year_disp,
        folder_chain             = folder_chain,
        filename_signals_block   = filename_signals_block,
        lifecycle_hint_str       = lifecycle_hint_str,
        asset_type_hint_str      = asset_type_hint_str,
        confidentiality_hint_str = confidentiality_hint_str,
        information_type         = meta["information_type"],
        is_data_hint             = meta.get("is_data_hint", "Unlikely"),
        content_sample           = content_indented,
    )

    # ── LLM call with one retry ───────────────────────────────────────────
    def _call(temp: float) -> dict:
        resp = client.chat.completions.create(
            model           = model,
            messages        = [
                {
                    "role":    "system",
                    "content": (
                        "You are an expert urban design data classifier. "
                        "Respond ONLY with a single valid JSON object. "
                        "No markdown, no commentary outside the JSON."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature     = temp,
            response_format = {"type": "json_object"},
        )
        raw = resp.choices[0].message.content

        # Strip accidental markdown fences (defensive)
        raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw, flags=re.IGNORECASE)

        return json.loads(raw)

    try:
        result = _call(temperature)
        result["llm"] = "ok"
        return result

    except (json.JSONDecodeError, KeyError):
        # Retry once at higher temperature — occasional fix for truncated JSON
        try:
            result = _call(max(temperature + 0.3, 0.3))
            result["llm"] = "ok (retry)"
            return result
        except Exception as e2:
            return _fallback(meta, f"json_error after retry: {e2}")

    except Exception as e:
        return _fallback(meta, str(e))


def _fallback(meta: dict, error_msg: str) -> dict:
    """Return a safe fallback classification with the error logged."""
    return {
        "_reasoning":       "Classification failed — see llm field for error.",
        "domain":           "Unknown",
        "scale":            "Non-spatial",
        "information_type": meta.get("information_type", "Unknown"),
        "lifecycle":        "Unknown",
        "governance":       "Unknown",
        "confidentiality":  "Standard",
        "asset_type":       "Unknown",
        "year":             meta.get("year"),
        "confidence":       "Low",
        "short_summary":    "Classification failed.",
        "llm":              f"error: {error_msg}",
    }