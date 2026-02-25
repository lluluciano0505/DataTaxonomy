import json
from pathlib import Path
from openai import OpenAI

# ── Prompt ────────────────────────────────────────────────────────────────
LAYER2_PROMPT = """\
You are an urban design data classifier working on a large-scale project.
Analyze the file metadata below and return ONLY valid JSON.

PROJECT CONTEXT (use as a hint, not an exhaustive list):
{project_context}

FILE:
  Filename:             {filename}
  Format:               {format}
  Size:                 {size_kb} KB
  Info type hint:       {information_type}
  Year (pre-extracted): {year}
  Folder path:          {folder_path}
  Is-data hint:         {is_data_hint}
  Content sample:
{content_sample}

The folder path is your most reliable signal when filename or content is ambiguous.
It often encodes project phase, discipline, and date — read it carefully.

The "Is-data hint" was computed by a rule engine before this prompt:
  Likely   — format or filename/folder strongly indicate a structured dataset
  Possible — content keywords suggest data, but not conclusive
  Unlikely — no data signals found

Use it as a weighted signal, not a hard rule. Override it if you are confident.

CLASSIFY using exactly these options:

DOMAIN (pick one):
  Administrative & Legal     — contracts, permits, legal agreements, regulatory
                               submissions, formal approvals, legal correspondence
  Architecture & Buildings   — building design, floor plans, sections, elevations,
                               facades, interior layouts, structural drawings
  Landscape & Public Realm   — landscape design, planting plans, hardscape, open space,
                               parks, streetscape, urban furniture
  Urban Planning & Massing   — masterplan drawings, land use, zoning, urban morphology,
                               massing studies, plot ratios, phasing plans
  Mobility & Transport       — roads, transit, parking, pedestrian and cycling networks
  Environment & Climate      — ecology, hydrology, wind, noise, sustainability
  Social & Demographics      — population, housing needs, community data
  Utilities & Infrastructure — water, energy, waste, telecoms, drainage systems
  Project Management         — schedules, budgets, meeting notes, RFIs, transmittals,
                               internal coordination, fee tracking
  Reference & Research       — precedents, standards, regulations, academic sources
  Unknown                    — cannot determine from available information

  RULES:
  - Site plans showing building footprints, land use, or plot boundaries
    → Urban Planning & Massing
  - Detailed floor plans, sections, elevations, facade or interior drawings
    → Architecture & Buildings
  - Planting, paving, open space, parks, streetscape, urban furniture
    → Landscape & Public Realm
  - If a drawing covers multiple disciplines, pick by the primary subject matter;
    use folder path and discipline prefix as tiebreaker
  - Folder or filename prefix signals:
      "Architecture/", "A-"  → Architecture & Buildings
      "Landscape/", "L-"     → Landscape & Public Realm
      "Masterplan/", "MP-", "Urban/" → Urban Planning & Massing
  - If a file is primarily about a SYSTEM (drainage, roads, power, telecoms)
    rather than physical form or massing → use the system's domain
  - Legal binding documents → Administrative & Legal
  - Operational and process documents → Project Management
  - .ifc and .rvt files → assign domain by discipline prefix in filename or folder
  - .geojson, .shp, .kml → use folder path to assign domain
  - Pick the most specific domain when in doubt

SCALE (pick one):
  Object / Parcel            — single building, plot, element, or detail
  Neighborhood / District    — urban block, district, or zone
  City / Municipal           — city-wide or full masterplan scope
  Regional / National        — regional, national, or cross-boundary
  Non-spatial                — no meaningful geographic scope

  RULES:
  - "masterplan" anywhere in path → City / Municipal
  - "title block", "detail", "element" in path → Object / Parcel
  - "district", "zone", "block" in path → Neighborhood / District
  - Non-geographic docs (contracts, emails, reports) → Non-spatial
  - Data files (is_data_hint=Likely) without clear spatial scope → Non-spatial

INFORMATION_TYPE (pick one):
  Schematic / Technical      — drawings, diagrams, CAD, BIM
  Quantitative / Tabular     — data tables, spreadsheets, statistics
  Narrative / Textual        — reports, descriptions, correspondence
  Spatial / Cartographic     — maps, GIS, geographic datasets
  Visual / Media             — photos, renders, presentations, linked assets
  Archive                    — compressed or bundled files
  Unknown

  RULES:
  - Only override the provided hint if you are confident it is wrong
  - Folder names like "Renders", "Links", "Images" → Visual / Media
  - is_data_hint=Likely + tabular format → Quantitative / Tabular
  - is_data_hint=Likely + spatial format → Spatial / Cartographic

LIFECYCLE (pick one):
  Brief / Concept            — early ideas, vision docs, RFPs, feasibility
  Schematic Design           — SD phase drawings, reports, presentations
  Design Development         — DD phase, developed drawings and specs
  Construction Documents     — CD phase, permit sets, tender packages, 100% submissions
  As-Built / Completed       — final built condition, completion records
  Reference / Archive        — background research, precedents, standards, regulations
  Unknown                    — cannot determine from available information

  RULES:
  - "100%", "final", "issued" in path → Construction Documents
  - "schematic", "SD" in path → Schematic Design
  - "updated", "revised", "DD", "render" in path → Design Development
  - Research papers, regulations, standards → Reference / Archive
  - Datasets and GIS layers → Reference / Archive unless folder path says otherwise

GOVERNANCE (pick one):
  Official    — produced by a government body, municipality, or regulatory authority
  Internal    — produced by the project team (lead firm or any consultant)
  External    — produced by a third party outside the project team
  Unknown     — cannot determine origin from available information

  SIGNALS — Official:
  - Authority/ministry names or abbreviations in filename or content
  - Regulatory formatting: approval stamps, official letterheads, decree structure
  - Prescriptive language ("shall", "is required to", "in accordance with Royal Decree...")
  - Permit numbers, planning reference codes, or official submission IDs

  SIGNALS — Internal:
  - Filename follows the project drawing code convention
  - Firm abbreviations from the project team in filename or content
  - WIP, draft, revision markers (Rev, R1, v2, ISSUED FOR REVIEW)
  - Internal report templates, meeting minutes, transmittal formats

  SIGNALS — External:
  - Stock imagery, generic media, or web-sourced content
  - Academic papers, research publications, or technical standards not by project team
  - Third-party datasets (census data, satellite imagery, commercial GIS layers)

  RULES:
  - A document can cite official sources but still be Internal
  - Unknown only if zero signals are available

CONFIDENTIALITY (pick one):
  Confidential  — contracts, fees, budgets, private correspondence, legal agreements
  Sensitive     — draft reports, internal memos, WIP coordination files
  Standard      — general project files, drawings, reports, public data

  RULES:
  - Default to Standard when in doubt — do not over-classify

ASSET_TYPE (pick one):
  Data         — structured/semi-structured datasets for analysis or GIS:
                 spreadsheets with measurement columns, GIS layers, survey tables,
                 sensor outputs, inventories, BIM property sets, census extracts
  Document     — narrative or formatted content: reports, specs, contracts,
                 correspondence, standards, presentations, PDFs
  Drawing      — geometric/spatial representations: CAD, BIM models,
                 floor plans, sections, elevations, site plans
  Media        — non-geometric visual content: photos, renders, videos, infographics
  Archive      — bundled or compressed collections of other assets
  Unknown      — cannot determine from available information

  RULES (first match wins):
  - is_data_hint=Likely AND format is .csv/.xlsx/.xls/.json → Data
  - is_data_hint=Likely AND format is .shp/.geojson/.kml → Data
  - is_data_hint=Likely AND format is .ifc → Data if property-set-heavy, else Drawing
  - is_data_hint=Possible → weigh content sample; default to Document/Drawing
    unless column headers or coordinate fields are visible
  - .dwg/.dxf/.rvt → Drawing (unless filename says "data" or "export")
  - .pdf with data table or schedule content → Data
  - .pdf with narrative or diagram content → Document
  - .pptx → Document
  - Images (.jpg/.png/.tiff) → Media
  - .zip → Archive
  - When in doubt: "Could this be imported into a database or GIS as-is?"
    If yes → Data, otherwise → Document

YEAR:
  - Use the pre-extracted year if it is not null
  - If null, extract from folder path (e.g. "2022_02_06" or "20220907" → 2022)
  - Return null only if genuinely not found anywhere

CONFIDENCE (pick one): High / Medium / Low
  - High:   3+ signals present and consistent, no contradictions
  - Medium: 1–2 signals clear, rest generic or mildly inconsistent
  - Low:    generic filename AND generic folder, or signals contradict each other

SHORT_SUMMARY: one sentence, max 15 words, describing the file's likely purpose.

Return ONLY this JSON, nothing else:
{{
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
    works cleanly when called from FastAPI/Celery workers.
    """
    file_path = Path(meta["file_path"])
    try:
        folder_path = str(file_path.parent.relative_to(input_path))
    except ValueError:
        folder_path = meta["folder"]

    prompt = LAYER2_PROMPT.format(
        project_context  = project_context,
        filename         = meta["filename"],
        format           = meta["format"],
        size_kb          = meta.get("size_kb", "?"),
        information_type = meta["information_type"],
        year             = meta.get("year") or "null",
        folder_path      = folder_path,
        is_data_hint     = meta.get("is_data_hint", "Unlikely"),
        content_sample   = (meta["content_sample"] or "")[:600],
    )

    try:
        resp = client.chat.completions.create(
            model           = model,
            messages        = [
                {"role": "system", "content": "You are an urban data classifier. Respond only with valid JSON."},
                {"role": "user",   "content": prompt},
            ],
            temperature     = temperature,
            response_format = {"type": "json_object"},
        )
        result = json.loads(resp.choices[0].message.content)
        result["llm"] = "ok"
        return result

    except Exception as e:
        return {
            "domain":           "Unknown",
            "scale":            "Non-spatial",
            "information_type": meta["information_type"],
            "lifecycle":        "Unknown",
            "governance":       "Unknown",
            "confidentiality":  "Standard",
            "asset_type":       "Unknown",
            "year":             meta.get("year"),
            "confidence":       "Low",
            "short_summary":    "Classification failed",
            "llm":              f"error: {e}",
        }
