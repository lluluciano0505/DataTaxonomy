# 🏙️ DataTaxonomy — Urban Asset Classifier

An automated file classification pipeline for large-scale urban design and architecture projects. Instead of manually sorting thousands of files, this tool attaches structured metadata to every file — domain, scale, lifecycle, risk level, and more — then visualizes the results in an interactive dashboard.

---

## How It Works

The pipeline runs in three layers:

| Layer | File | What it does |
|-------|------|--------------|
| **Layer 1** | `layer1.py` | Rule-based: extracts file metadata, content sample, year, data hint |
| **Layer 2** | `layer2.py` | LLM-based: classifies domain, scale, lifecycle, asset type, governance |
| **Layer 3** | `layer3.py` | Rule-based: risk assessment, flags files needing manual review |

Output is a CSV where every file gets 20 structured fields, ready for filtering or analysis.

---

## Example Output

| filename | domain | scale | lifecycle | risk_level | governance |
|----------|--------|-------|-----------|------------|------------|
| Traffic_Report_2024.xlsx | Mobility & Transport | Neighborhood / District | As-Built / Completed | Low | Official |
| KSP-HL-DD-A-DWG-0042.dwg | Architecture & Buildings | Object / Parcel | Design Development | Medium | Internal |

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
MODEL=google/gemini-2.0-flash-001
```

### 3. Configure your project
Edit `test_run.py` — update `PROJECT` and `INPUT_PATH` to match your project:
```python
PROJECT = {
    "name":       "Your Project Name",
    "location":   "City, Country",
    "year_range": [2020, 2025],
    "lead_firm":  "Your Firm",
    ...
}
INPUT_PATH = Path.home() / "Desktop" / "YourProjectFolder"
```

### 4. Run the classifier
```bash
python test_run.py
```
Outputs `test_output.csv` in the project root.

### 5. Launch the dashboard
```bash
streamlit run dashboard.py
```

---

## Project Structure

```
DataTaxonomy/
├── core/
│   ├── __init__.py
│   ├── layer1.py        # Metadata extraction
│   ├── layer2.py        # LLM classification
│   ├── layer3.py        # Risk assessment
│   └── pipeline.py      # Batch runner + CSV output
├── .env                 # API key (local only, not uploaded)
├── .env.example         # Key template
├── .gitignore
├── requirements.txt
├── test_run.py          # Entry point
└── dashboard.py         # Streamlit dashboard
```

---

## Supported File Formats

`.pdf` `.docx` `.pptx` `.xlsx` `.csv` `.json` `.txt`
`.dwg` `.dxf` `.ifc` `.rvt`
`.jpg` `.png` `.tiff`
`.shp` `.geojson` `.kml`
`.eml` `.msg` `.zip`

---

## Classification Fields

| Field | Options |
|-------|---------|
| **Domain** | Architecture & Buildings, Landscape & Public Realm, Urban Planning & Massing, Mobility & Transport, Environment & Climate, Social & Demographics, Utilities & Infrastructure, Administrative & Legal, Project Management, Reference & Research |
| **Scale** | Object / Parcel, Neighborhood / District, City / Municipal, Regional / National, Non-spatial |
| **Lifecycle** | Brief / Concept, Schematic Design, Design Development, Construction Documents, As-Built / Completed, Reference / Archive |
| **Asset Type** | Data, Document, Drawing, Media, Archive |
| **Governance** | Official, Internal, External, Unknown |
| **Confidentiality** | Confidential, Sensitive, Standard |
| **Risk Level** | High, Medium, Low |

---

## Dashboard

The Streamlit dashboard includes:
- **Coverage Map** — heatmap of files by Domain × Scale, highlights data gaps
- **Trust Score** — governance breakdown (Official / Internal / External)
- **Timeline View** — files per year coloured by lifecycle stage
- **Risk Breakdown** — risk distribution per domain
- **File Table** — filterable list with download button

---

## Tech Stack

- **Python 3.9+**
- **OpenRouter API** (Gemini 2.0 Flash or any compatible model)
- **Streamlit** + **Plotly** for the dashboard
- **pypdf**, **python-docx**, **pandas**, **Pillow** for content extraction

---

## Cost Estimate

Using `google/gemini-2.0-flash-001` via OpenRouter:
- 100 files ≈ $0.05–0.10
- 400 files ≈ $0.20–0.50
- 3,000+ files ≈ $2–5
