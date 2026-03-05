# 🧰 DataTaxonomy — Other Run Methods (Non-web flow)

> This file keeps only non-web alternatives.
> For the primary flow and setup, see [README.md](../README.md).

---

## 1) Command Line (CLI)

### Standard run
```bash
python main.py
```

### Process only (no dashboard)
```bash
python main.py --no-dashboard
```

### Parallel processing (faster)
```bash
python main.py --parallel 8
```

### Use a custom config file
```bash
python main.py --config myconfig.yaml
```

### Help
```bash
python main.py --help
```

---

## 2) Conda example

```bash
conda run -p /opt/anaconda3 python main.py --no-dashboard
```

---

## Recommendations

- For the simplest workflow: use the web flow (see [README.md](../README.md))
- For automation / batch / CI: use the CLI (`python main.py ...`)
