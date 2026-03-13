# 🎯 DataTaxonomy — Configuration Guide

> This document focuses only on `config.yaml` and related settings.
> For setup and running instructions, see [README.md](../README.md).

## Configuration File (config.yaml)

All project settings are in **config.yaml** — no code changes needed!

### Project Metadata
```yaml
project:
  name: "Your Project Name"
  location: "City, Country"
  year_range: [2020, 2026]
  lead_firm: "Architecture Firm"
  consultants:
    - "Consultant 1"
    - "Consultant 2"
  authorities:
    - "Authority 1"
  drawing_code: "PREFIX-[FIRM]-[PHASE]-[DISCIPLINE]-[TYPE]-[NUMBER]"
  notes: "Any project notes"
```

### Input/Output Paths
```yaml
paths:
  input_dir: "~/Desktop/MyProject"  # Folder with files to process
  output_csv: "results.csv"         # Output filename
```

### Processing Settings
```yaml
processing:
  sample_n: 20           # Number of files to sample (null = all files)
  model: "google/gemini-2.0-flash-001"  # LLM model from OpenRouter
```

### Dashboard Settings
```yaml
dashboard:
  port: 8501             # Streamlit port
  auto_launch: true      # Auto-open browser
```

## Environment Variables

Set in `.env`:
- `OPENROUTER_API_KEY` — Your OpenRouter API key (required)
- `MODEL` — Override the config.yaml model (optional)

## Command Line Options

```bash
# Run with custom config file
python main.py --config my_config.yaml
```

## Switching Between Projects

Create separate config files:

```bash
# Project 1
cp config.yaml fælledby.yaml
nano fælledby.yaml

# Project 2
cp config.yaml copenhagen.yaml
nano copenhagen.yaml

# Run each
python main.py --config fælledby.yaml
python main.py --config copenhagen.yaml
```

## Path Examples

**Absolute path:**
```yaml
input_dir: "/Users/username/Documents/MyProject"
```

**Relative to home (~):**
```yaml
input_dir: "~/Desktop/MyProject"
input_dir: "~/Documents/Projects/MyProject"
```

**Current directory:**
```yaml
input_dir: "./data"
```

## Troubleshooting

**"Configuration file not found"**
- Make sure `config.yaml` exists in the project root
- Use `--config` flag to specify a different path

**"Input directory not found"**
- Check the `paths.input_dir` path in config.yaml
- Use absolute path or expand `~` correctly
