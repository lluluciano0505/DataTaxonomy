# 🏙️ DataTaxonomy — Urban Asset Classifier

An automated file classification pipeline for large-scale urban design and architecture projects. Instead of manually sorting thousands of files, this tool attaches structured metadata to every file — domain, scale, lifecycle, confidentiality, risk level, and more — then visualizes the results in an interactive dashboard.

**Latest improvements:**
- 🚀 **Parallel processing** — process 400+ files 4–8× faster
- 🎨 **Enhanced CAD extraction** — intelligently parse DWG/Revit file names (discipline, phase, drawing code)
- 🧠 **Smart confidentiality detection** — LLM judges semantic context, not just keyword matching (avoids false positives on technical drawings)
- 📅 **Smart year detection** — validates years to prevent misclassification (2000+ only by default)
- 📂 **Interactive file explorer** — click to open files directly from dashboard

---

## How It Works

The pipeline runs in three layers:

| Layer | File | What it does |
|-------|------|--------------|
| **Layer 1** | `core/layer1.py` | Rule-based: extracts file metadata, content sample, year, data hints, CAD metadata |
| **Layer 2** | `core/layer2.py` | LLM-based: classifies domain, scale, lifecycle, asset type, governance, confidentiality |
| **Layer 3** | `core/layer3.py` | Rule-based: risk assessment, age analysis, flags files needing manual review |

Output is a CSV where every file gets 20+ structured fields, ready for filtering or analysis.

---

## Example Output

| filename | domain | scale | lifecycle | review_priority | confidentiality |
|----------|--------|-------|-----------|-----------------|-----------------|
| Budget_2024.pdf | Project Management | Non-spatial | As-Built / Completed | Critical | Confidential |
| KSP-HL-DD-A-DWG-0042.dwg | Architecture & Buildings | Object / Parcel | Design Development | Low | Standard |
| Slope_Analysis_30pct.pdf | Landscape & Public Realm | Neighborhood / District | Design Development | Low | Standard |

---

## Quick Start

### 1. Clone and install
```bash
git clone https://github.com/your-username/DataTaxonomy.git
cd DataTaxonomy
pip install -r requirements.txt
```

### 2. Set up your API key
```bash
cp .env.example .env
```
Edit `.env` and add your [OpenRouter](https://openrouter.ai) API key:
```
OPENROUTER_API_KEY=your-key-here
```

### 3. Configure your project

**Web UI (recommended, primary flow)**
```bash
streamlit run config_ui.py
```
Open the friendly configuration UI without editing YAML. Includes:
- 📋 Project info (name, location, year range)
- 📂 File paths
- ⚡ Processing settings (file count, LLM model, parallel workers)
- 🎨 Dashboard and analysis options

> Note: the docs keep the web flow as the default.
> Other launch methods (CLI / GUI / scripts) are in [docs/RUN_METHODS.md](docs/RUN_METHODS.md)

### 4. Run the classifier

Click `▶️ START PROCESSING` in the `config_ui.py` page.

Outputs `results.csv` in the project root.

### 5. Launch the dashboard
```bash
streamlit run dashboard.py
```
Outputs appear at **http://localhost:8502** with:
- 📊 Overview stats (total files, critical reviews, data assets)
- 🗺️ Domain × Scale heatmap
- 📈 Timeline view (files per year by lifecycle)
- 🔒 Confidentiality breakdown
- 📁 **Interactive file explorer** — select, click to open in Finder or default app

---

## Project Structure

```
DataTaxonomy/
├── core/
│   ├── __init__.py
│   ├── layer1.py              # Metadata extraction, CAD parsing
│   ├── layer2.py              # LLM classification
│   ├── layer3.py              # Risk & age analysis
│   └── pipeline.py            # Batch runner, parallel support
├── pic/
│   └── DT.jpg                 # Application banner/logo
├── config.yaml                # Project config (no code edits needed)
├── config_loader.py           # Config parser
├── config_ui.py               # Web-based config manager ⭐ NEW
├── main.py                    # Entry point (CLI)
├── dashboard.py               # Results dashboard
├── requirements.txt
├── .env.example
└── README.md
```

---

## Supported File Formats

**Documents:**
`.pdf` `.docx` `.doc` `.txt` `.pptx`

**Data:**
`.xlsx` `.xls` `.csv` `.json`

**CAD & Technical:**
`.dwg` `.dxf` `.ifc` `.rvt` `.nwd`

**Spatial:**
`.shp` `.geojson` `.kml` `.gpkg`

**Media:**
`.jpg` `.jpeg` `.png` `.tiff` `.mp4` `.mov`

**Other:**
`.eml` `.msg` `.zip` `.7z` `.rar`
---

## Classification Fields

| Field | Options | Notes |
|-------|---------|-------|
| **Domain** | Architecture & Buildings, Landscape & Public Realm, Urban Planning & Massing, Mobility & Transport, Environment & Climate, Social & Demographics, Utilities & Infrastructure, Administrative & Legal, Project Management, Reference & Research | LLM infers from filename, folder, and content |
| **Scale** | Object / Parcel, Neighborhood / District, City / Municipal, Regional / National, Non-spatial | Reflects geographic scope |
| **Lifecycle** | Brief / Concept, Schematic Design, Design Development, Construction Documents, As-Built / Completed, Reference / Archive | Derived from folder path + content signals |
| **Asset Type** | Data, Document, Drawing, Media, Archive | Data = structured tables/GIS; Drawing = CAD/plans |
| **Governance** | Official, Internal, External, Unknown | Source authority (client, internal, third-party) |
| **Confidentiality** | Confidential, Sensitive, Standard | LLM judges semantic context (not just rules) |
| **Review Priority** | Critical, High, Medium, Low | Risk assessment: combines confidentiality, age, domain, confidence |
| **Year** | Extracted from filename, content, or file mtime | Validates 2000–present (avoids historical errors) |
| **Age Warning** | — | Flags files predating project or significantly aged |

---

## Smart Features

### 🚀 Parallel Processing
Process large batches **4–8× faster**:
```bash
python main.py --parallel 8
```
Uses ThreadPoolExecutor to classify files concurrently while respecting API rate limits.

### 🎨 CAD Intelligence
DWG/Revit files now extract:
- **Drawing code** (e.g., `A-001`, `SK-024`)
- **Discipline** (ARCH, STRUC, MEP, LAND, CIVIL)
- **Phase** (SK=Sketch, DD=Design Dev, CD=Construction Docs, AB=As-Built)
- **AutoCAD version** (2018–2021, 2013–2017, etc.)

Example DWG recognition:
```
FLB-HL-DD-A-D-001.dwg
  → Drawing: FLB-HL-DD-A-D-001
  → Discipline: Architecture
  → Phase: Design Development
  → Version: AutoCAD 2018–2021
```

### 🧠 Semantic Confidentiality Detection
LLM judges actual context instead of just rules:
- ✅ "30% slope" in landscape drawing → **Standard** (design spec)
- ✅ "30% markup on budget" in cost plan → **Confidential** (business doc)
- ✅ "$500 material cost" in spec → **Standard** (technical)
- ✅ "$500 fee markup" in proposal → **Confidential** (commercial)

### 📅 Smart Year Extraction
- Validates years 2000–present (rejects 1915, 1950, etc.)
- **Sources in priority order:** filename → content frequency → file mtime
- **Confidence levels:** high (filename), medium (content ≥3 hits), low (mtime)

### 📂 Interactive Dashboard
Click any file in the table to:
- **Show in Finder** — locate file in folder
- **Open File** — launch with default application
- **View metadata** — size, type, priority, summary

---

## Dashboard Features

- **Overview Stats** — total files, critical reviews, data assets, confidentiality breakdown
- **Domain × Scale Heatmap** — visual gap analysis
- **Trust Scores** — governance breakdown (Official/Internal/External/Unknown)
- **Timeline View** — files per year by lifecycle stage (spot aging issues)
- **Risk Breakdown** — critical/high/medium/low distribution by domain
- **File Explorer** — select, open in Finder, or download filtered CSV

---

## Tech Stack

- **Python 3.10+**
- **OpenRouter API** (Gemini 2.0 Flash or any LLM compatible with OpenAI API)
- **Streamlit** + **Plotly** for interactive dashboard
- **concurrent.futures** for parallel processing
- **pypdf**, **python-docx**, **openpyxl**, **pandas**, **Pillow** for content extraction

---

## Performance

| Files | Time (Serial) | Time (Parallel ×8) | Cost |
|-------|---------------|-------------------|------|
| 100 | ~8 min | ~2 min | $0.05–0.10 |
| 400 | ~30 min | ~4 min | $0.20–0.50 |
| 1,000 | ~75 min | ~10 min | $0.50–1.00 |
| 3,000+ | ~4 hours | ~30 min | $2–5 |

Estimated using `google/gemini-2.0-flash-001` @ ~$0.075/M tokens (input).

---

## Configuration

Edit `config.yaml` to customize:

```yaml
project:
  name: "Fælledby Masterplan"              # Project name
  location: "Copenhagen, Denmark"           # Location
  year_range: [2019, 2026]                 # Project timeline
  lead_firm: "Henning Larsen"              # Lead designer
  consultants: ["MOE", "BirdLife Denmark"] # Team members
  authorities: ["Copenhagen Municipality"] # Approving bodies

paths:
  input_dir: "~/Desktop/Project"           # Folder to process
  output_csv: "results.csv"                # Output filename

processing:
  sample_n: 400                            # Files to process (null = all)
  model: "google/gemini-2.0-flash-001"   # LLM model

dashboard:
  port: 8502                               # Dashboard port
  auto_launch: true                        # Open browser on start

age_analysis:
  warn_predates_years: 10                  # Warn if 10+ years before project
  warn_postproject_years: 3                # Warn if 3+ years after project
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `OPENROUTER_API_KEY not found` | Ensure `.env` file exists with valid key |
| `Input directory not found` | Check `config.yaml` paths (use absolute or ~/home shortcuts) |
| `LLM classification failed` | Increase timeouts, check API rate limits, switch to faster model |
| `Dashboard won't open` | Check port 8502 is free; manually visit `http://localhost:8502` |
| `Files misclassified as Confidential` | LLM semantic judgment was overridden; review content sample in CSV |

---

## Deploy (Streamlit Community Cloud)

1) Push this repo to GitHub.
2) Go to https://streamlit.io/cloud and create a new app.
3) Select this repo and set the app file to `config_ui.py` (or `dashboard.py` for the dashboard-only view).
4) (Optional) Add secrets in the Streamlit Cloud UI if you need `OPENROUTER_API_KEY`.

Notes:
- Streamlit Cloud uses `requirements.txt` automatically.
- Default port is handled by Streamlit Cloud; no manual port configuration needed.

## License

MIT — see LICENSE file for details.

---

## Contact

Questions or suggestions? Open an issue or contact the development team.
