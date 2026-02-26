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


# ── Lifecycle pre-hint map ────────────────────────────────────────────────
# Maps AEC status codes to candidate lifecycle values, injected into the prompt
# as a weighted hint.  The LLM can override this if other signals contradict it.
_STATUS_TO_LIFECYCLE_HINT: dict[str, str] = {
    # Construction Documents / tender stage
    "IFC":      "Construction Documents",   # Issued For Construction
    "AFC":      "Construction Documents",   # Approved For Construction
    "IFT":      "Construction Documents",   # Issued For Tender
    "IFB":      "Construction Documents",   # Issued For Bid
    "100%":     "Construction Documents",
    "ISSUED":   "Construction Documents",
    # Design Development
    "IFR":      "Design Development",       # Issued For Review
    "IFI":      "Design Development",       # Issued For Information
    "DD":       "Design Development",
    "REVIEW":   "Design Development",
    "FOR REVIEW": "Design Development",
    "FOR COMMENT": "Design Development",
    # Schematic / Concept
    "CONCEPT":  "Schematic Design",
    "PRELIMINARY": "Schematic Design",
    "SD":       "Schematic Design",
    # WIP / Draft (could be any phase — signal is weak)
    "WIP":      None,
    "DRAFT":    None,
    # Post-construction
    "AS-BUILT": "As-Built / Completed",
    "ASBUILT":  "As-Built / Completed",
    "RECORD":   "As-Built / Completed",
    "APPROVED": "As-Built / Completed",
    "FINAL":    "As-Built / Completed",     # ambiguous but lean late-stage
    # Superseded → archive
    "SUPERSEDED": "Reference / Archive",
}


def _lifecycle_hint(meta: dict) -> str | None:
    """Return a lifecycle hint string derived from filename_signals.status_tag, or None."""
    signals = meta.get("filename_signals") or {}
    tag = (signals.get("status_tag") or "").upper()
    return _STATUS_TO_LIFECYCLE_HINT.get(tag)


# ── Data formats that always → asset_type = Data ─────────────────────────
_HARD_DATA_FORMATS = {
    "CSV", "XLSX", "XLS", "JSON", "SHP", "GEOJSON", "KML", "GPKG",
}

_DATA_NAME_SIGNALS = [
    "data", "dataset", "statistics", "survey", "census", "inventory",
    "register", "schedule", "matrix", "gis", "layer", "export", "analysis",
    "measurement", "count", "index", "database",
]

def _asset_type_hint(meta: dict) -> str | None:
    """
    Pre-compute asset_type from format + is_data_hint + filename.
    Returns 'Data', 'Drawing', or None (let LLM decide).
    """
    fmt      = (meta.get("format") or "").upper()
    hint     = meta.get("is_data_hint", "Unlikely")
    path_low = (meta.get("file_path") or "").lower()
    filename = (meta.get("filename") or "").lower()

    if fmt in _HARD_DATA_FORMATS:
        return "Data"

    if fmt in {"DWG", "DXF", "RVT", "IFC", "NWD"}:
        return "Drawing"

    if hint == "Likely":
        combined = path_low + " " + filename
        if any(k in combined for k in _DATA_NAME_SIGNALS):
            return "Data"
        return "Data"

    return None


# ── Confidentiality keyword maps ──────────────────────────────────────────
_CONFIDENTIAL_KEYWORDS = [
    "contract", "contracts", "agreement", "nda", "loa", "loi", "mou",
    "fee", "fees", "budget", "budgets", "cost", "costs", "pricing",
    "invoice", "invoices", "payment", "payments", "financial", "finance",
    "salary", "salaries", "remuneration",
    "legal", "litigation", "arbitration", "dispute",
    "personal", "private", "confidential",
    "tender_price", "bid_price", "rate_card",
]

_SENSITIVE_KEYWORDS = [
    "internal", "draft", "wip", "memo", "minutes", "meeting_minutes",
    "rfi", "transmittal", "correspondence",
    "staff", "personnel", "hr", "preliminary",
]

def _confidentiality_hint(meta: dict) -> str | None:
    """
    Pre-compute confidentiality from filename + folder path keywords.
    Returns 'Confidential', 'Sensitive', or None (let LLM decide).
    """
    filename  = (meta.get("filename") or "").lower()
    path_low  = (meta.get("file_path") or "").lower()
    combined  = filename + " " + path_low
    seg_str   = " ".join(s.lower() for s in (meta.get("path_segments") or []))

    if any(k in combined for k in _CONFIDENTIAL_KEYWORDS):
        return "Confidential"
    if any(k in seg_str for k in _CONFIDENTIAL_KEYWORDS):
        return "Confidential"
    if any(k in combined for k in _SENSITIVE_KEYWORDS):
        return "Sensitive"
    if any(k in seg_str for k in _SENSITIVE_KEYWORDS):
        return "Sensitive"
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
    """Render filename_signals as a compact bullet block for the prompt."""
    signals = meta.get("filename_signals") or {}
    if not signals:
        return "  (not available — old Layer 1 output)"

    lines = []
    if signals.get("discipline_code"):
        lines.append(f"  Discipline:    {signals['discipline_code']}")
    if signals.get("status_tag"):
        lines.append(f"  Status:        {signals['status_tag']}")
    if signals.get("version"):
        lines.append(f"  Version:       {signals['version']}")
    if signals.get("drawing_number"):
        lines.append(f"  Drawing No.:   {signals['drawing_number']}")
    if signals.get("has_date_in_name"):
        lines.append("  Date in name:  yes")

    return "\n".join(lines) if lines else "  (no AEC signals detected in filename)"


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
FILENAME SIGNALS  (pre-parsed by Layer 1)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{filename_signals_block}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
LIFECYCLE HINT  (pre-computed from status tag)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {lifecycle_hint_str}

  This hint comes from the status code in the filename (e.g. IFC, AFC, AS-BUILT).
  It is a strong signal when present.  Override it ONLY if the folder path or
  content clearly contradicts it.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ASSET TYPE HINT  (pre-computed from format + Layer 1 data signals)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {asset_type_hint_str}

  This hint was computed from file format and keyword analysis BEFORE this call.
  Treat it as a strong default for asset_type.
  Override ONLY if the content sample clearly shows it is wrong.
  Raw Layer 1 data signal: {is_data_hint}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONFIDENTIALITY HINT  (pre-computed from filename + folder keywords)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {confidentiality_hint_str}

  This hint was computed by matching confidentiality keywords in the filename
  and folder path (contract, fee, budget, nda, legal, invoice, draft, wip, memo...).
  Treat it as a strong default for confidentiality.
  Override ONLY if the content sample clearly contradicts it.

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
