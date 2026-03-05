# 🎯 DataTaxonomy — Quick Start Guide

This file keeps only the shortest onboarding path. All other details are in the main docs.

## 3-minute setup

1) Install dependencies:

```bash
pip install -r requirements.txt
```

2) Configure the API key:

```bash
cp .env.example .env
```

Fill in `OPENROUTER_API_KEY` in `.env`.

3) Open the web configurator and start processing:

```bash
streamlit run config_ui.py --server.port 8502
```

Click `▶️ START PROCESSING` on the page, download the CSV when finished, and follow the prompt to launch the dashboard.

---

## More resources

- Full project description and features: see [README.md](../README.md)
- Configuration fields: see [CONFIG.md](CONFIG.md)
- Other run methods (CLI/GUI/scripts): see [RUN_METHODS.md](RUN_METHODS.md)
