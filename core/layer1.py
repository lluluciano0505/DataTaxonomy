import re
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── Info type map ─────────────────────────────────────────────────────────
INFO_TYPE_MAP = {
    ".pdf":     "Document — see content_sample",
    ".docx":    "Narrative / Textual",
    ".doc":     "Narrative / Textual",
    ".txt":     "Narrative / Textual",
    ".pptx":    "Visual / Presentation",
    ".xlsx":    "Quantitative / Tabular",
    ".xls":     "Quantitative / Tabular",
    ".csv":     "Quantitative / Tabular",
    ".json":    "Quantitative / Tabular",
    ".dwg":     "Schematic / Technical",
    ".dxf":     "Schematic / Technical",
    ".ifc":     "Schematic / BIM",
    ".rvt":     "Schematic / BIM",
    ".jpg":     "Visual / Media",
    ".jpeg":    "Visual / Media",
    ".png":     "Visual / Media",
    ".tiff":    "Visual / Media",
    ".tif":     "Visual / Media",
    ".shp":     "Spatial / Cartographic",
    ".geojson": "Spatial / Cartographic",
    ".kml":     "Spatial / Cartographic",
    ".eml":     "Narrative / Email",
    ".msg":     "Narrative / Email",
    ".zip":     "Archive",
}

# ── PDF extraction config ─────────────────────────────────────────────────
PDF_HEAD_PAGES = 3
PDF_TAIL_PAGES = 2
PDF_MID_SAMPLE = 2
PDF_MAX_CHARS  = 2400
DEFAULT_MAX_CHARS = 800

# ── Data detection config ─────────────────────────────────────────────────
_DATA_FORMATS = {".xlsx", ".xls", ".csv", ".json", ".shp", ".geojson", ".kml"}
_DATA_POSSIBLE_FORMATS = {".ifc", ".dxf"}

_DATA_NAME_KEYWORDS = [
    "data", "dataset", "statistics", "statistic", "survey", "census",
    "database", "db", "gis", "layer", "inventory", "index", "register",
    "schedule", "matrix", "table", "count", "measurement", "sensor",
    "output", "export", "report_data", "analysis",
]

_DATA_CONTENT_KEYWORDS = [
    "latitude", "longitude", "geometry", "coordinates", "feature",
    "field_name", "column", "row_count", "record", "attribute",
    "timestamp", "unit:", "value:", "measurement", "total:", "sum:",
]


# ── Year extraction ───────────────────────────────────────────────────────
def _find_years_in_text(text: str) -> list[str]:
    current = datetime.now().year
    hits    = re.findall(r"\b(20\d{2}|19\d{2})\b", text)
    return [h for h in hits if int(h) <= current]


def _extract_year(filename: str, content: str = "") -> Optional[str]:
    filename_years = _find_years_in_text(filename)
    if filename_years:
        return max(filename_years, key=int)

    cleaned = re.sub(r"\b[A-Z]{1,5}[\s\-]\d{3,6}[-:]\d{2,4}\b", "", content)
    cleaned = re.sub(r"©\s*\d{4}", "", cleaned)
    content_years = _find_years_in_text(cleaned)
    if not content_years:
        return None

    from collections import Counter
    freq       = Counter(content_years)
    max_freq   = max(freq.values())
    candidates = [y for y, c in freq.items() if c == max_freq]
    return max(candidates, key=int)


# ── Coverage helpers ──────────────────────────────────────────────────────
def _cov_pages(read: list[int], total: int) -> str:
    return f"{len(read)}/{total} pages sampled"

def _cov_chars(content: str, cap: int, label: str = "") -> str:
    truncated = len(content) >= cap
    base = f"truncated at {cap} chars" if truncated else f"full content ({len(content)} chars)"
    return f"{label} — {base}" if label else base


# ── Data hint ─────────────────────────────────────────────────────────────
def _is_data_hint(file_path: Path, content: str) -> str:
    ext        = file_path.suffix.lower()
    path_lower = str(file_path).lower()

    if ext in _DATA_FORMATS:
        return "Likely"

    if ext in _DATA_POSSIBLE_FORMATS:
        if any(k in path_lower for k in _DATA_NAME_KEYWORDS):
            return "Likely"
        if any(k in content.lower() for k in _DATA_CONTENT_KEYWORDS):
            return "Possible"
        return "Unlikely"

    if any(k in path_lower for k in _DATA_NAME_KEYWORDS):
        return "Likely"

    if content and any(k in content.lower() for k in _DATA_CONTENT_KEYWORDS):
        return "Possible"

    return "Unlikely"


# ── Content extraction ────────────────────────────────────────────────────
def _extract_content(file_path: Path) -> tuple[str, Optional[int], str]:
    ext = file_path.suffix.lower()

    if ext == ".pdf":
        try:
            from pypdf import PdfReader
            r     = PdfReader(str(file_path))
            pages = len(r.pages)
            head  = list(range(min(PDF_HEAD_PAGES, pages)))
            tail  = list(range(max(0, pages - PDF_TAIL_PAGES), pages))
            mid   = []
            if pages > PDF_HEAD_PAGES + PDF_TAIL_PAGES + 2 and PDF_MID_SAMPLE > 0:
                mid_start = PDF_HEAD_PAGES
                mid_end   = pages - PDF_TAIL_PAGES
                step      = max(1, (mid_end - mid_start) // (PDF_MID_SAMPLE + 1))
                mid = [mid_start + step * (i + 1) for i in range(PDF_MID_SAMPLE)
                       if mid_start + step * (i + 1) < mid_end]
            page_indices = list(dict.fromkeys(head + mid + tail))
            parts = []
            for i in page_indices:
                text = (r.pages[i].extract_text() or "").strip()
                if text:
                    parts.append(f"[p{i + 1}] {text}")
            if parts:
                raw      = "\n".join(parts)
                content  = raw[:PDF_MAX_CHARS]
                coverage = _cov_pages(page_indices, pages)
                if len(raw) > PDF_MAX_CHARS:
                    coverage += f" — truncated at {PDF_MAX_CHARS} chars"
            else:
                size_kb  = file_path.stat().st_size // 1024
                content  = (f"[PDF: no extractable text — likely scanned drawing or print export]\n"
                            f"Pages: {pages} | Size: {size_kb} KB\n"
                            f"Infer content from filename and folder path.")
                coverage = f"{pages} pages — no text layer detected"
        except Exception as e:
            content, pages, coverage = f"[PDF error: {e}]", None, "extraction failed"
        return content, pages, coverage

    elif ext in (".docx", ".doc"):
        try:
            import docx
            doc        = docx.Document(str(file_path))
            para_texts = [p.text for p in doc.paragraphs[:20] if p.text.strip()]
            table_texts = []
            for tbl_idx, table in enumerate(doc.tables[:3]):
                table_texts.append(f"[Table {tbl_idx + 1}]")
                for row in table.rows[:3]:
                    row_text = " | ".join(c.text.strip() for c in row.cells if c.text.strip())
                    if row_text:
                        table_texts.append(row_text)
            parts    = para_texts + (["[Tables:]"] + table_texts if table_texts else [])
            content  = "\n".join(parts)[:DEFAULT_MAX_CHARS]
            coverage = (f"{len(para_texts)} paragraphs"
                        + (f" + {len(doc.tables)} table(s) sampled" if doc.tables else ""))
        except Exception as e:
            content  = f"[DOCX error — likely legacy .doc binary: {e}]"
            coverage = "extraction failed"
        return content, None, coverage

    elif ext == ".pptx":
        try:
            from pptx import Presentation
            prs        = Presentation(str(file_path))
            all_slides = list(prs.slides)
            total      = len(all_slides)
            head_idx   = list(range(min(3, total)))
            tail_idx   = list(range(max(0, total - 2), total))
            indices    = list(dict.fromkeys(head_idx + tail_idx))
            texts = []
            for i in indices:
                slide_texts = [shape.text.strip() for shape in all_slides[i].shapes
                               if hasattr(shape, "text") and shape.text.strip()]
                if slide_texts:
                    texts.append(f"[slide {i + 1}] " + " / ".join(slide_texts))
            content  = "\n".join(texts)[:DEFAULT_MAX_CHARS]
            coverage = f"{len(indices)}/{total} slides sampled (head+tail)"
        except Exception as e:
            content, coverage = f"[PPTX error: {e}]", "extraction failed"
        return content, None, coverage

    elif ext in (".xlsx", ".xls"):
        try:
            import pandas as pd
            xl      = pd.ExcelFile(str(file_path))
            df      = pd.read_excel(file_path, sheet_name=xl.sheet_names[0], nrows=5)
            headers = list(df.columns)
            content = (f"Sheets: {xl.sheet_names}\nColumns: {headers}\n"
                       f"{df.head(5).to_string()}")[:DEFAULT_MAX_CHARS]
            coverage = f"sheet 1 of {len(xl.sheet_names)}, first 5 rows + headers"
        except Exception as e:
            content, coverage = f"[Excel error: {e}]", "extraction failed"
        return content, None, coverage

    elif ext == ".csv":
        try:
            import pandas as pd
            df      = pd.read_csv(file_path, nrows=5, encoding="utf-8", errors="replace")
            headers = list(df.columns)
            content = (f"Columns: {headers}\n{df.head(5).to_string()}")[:DEFAULT_MAX_CHARS]
            coverage = "first 5 rows + headers"
        except Exception as e:
            content, coverage = f"[CSV error: {e}]", "extraction failed"
        return content, None, coverage

    elif ext in (".txt", ".json"):
        try:
            raw      = file_path.read_text(encoding="utf-8", errors="replace")
            content  = raw[:DEFAULT_MAX_CHARS]
            coverage = _cov_chars(raw, DEFAULT_MAX_CHARS)
        except Exception as e:
            content, coverage = f"[Text error: {e}]", "extraction failed"
        return content, None, coverage

    elif ext == ".dwg":
        return "[DWG binary — filename and folder path signals only]", None, "binary, no extraction"

    elif ext == ".dxf":
        try:
            raw       = file_path.read_text(encoding="utf-8", errors="replace")[:1200]
            layers    = re.findall(r"(?<=\n  2\n)[A-Z0-9_\-]+(?=\n)", raw)
            layer_str = ", ".join(dict.fromkeys(layers[:20]))
            content   = (f"[DXF layers: {layer_str}]\n{raw[:400]}" if layer_str else raw[:400])
            coverage  = f"{len(layers)} layer names extracted"
        except Exception as e:
            content, coverage = f"[DXF error: {e}]", "extraction failed"
        return content, None, coverage

    elif ext == ".rvt":
        return "[Revit binary — filename and folder path signals only]", None, "binary, no extraction"

    elif ext == ".ifc":
        try:
            raw      = file_path.read_text(encoding="utf-8", errors="replace")
            content  = raw[:DEFAULT_MAX_CHARS]
            coverage = _cov_chars(raw, DEFAULT_MAX_CHARS, "IFC header")
        except Exception as e:
            content, coverage = f"[IFC error: {e}]", "extraction failed"
        return content, None, coverage

    elif ext in (".jpg", ".jpeg", ".png", ".tiff", ".tif"):
        try:
            from PIL import Image
            from PIL.ExifTags import TAGS
            img           = Image.open(file_path)
            size_kb       = file_path.stat().st_size // 1024
            exif_year     = ""
            exif_date_raw = ""
            try:
                exif_data = img._getexif() or {}
                for tag_id, val in exif_data.items():
                    if TAGS.get(tag_id) == "DateTimeOriginal":
                        exif_date_raw = str(val)[:10]
                        exif_year     = exif_date_raw[:4]
                        break
            except Exception:
                pass
            exif_tag = f" exif_year={exif_year}" if exif_year else ""
            content  = f"[Image {img.width}x{img.height}px mode={img.mode} size={size_kb}KB{exif_tag}]"
            coverage = "EXIF metadata" + (f" — shoot date {exif_date_raw}" if exif_date_raw else " — no EXIF date")
        except Exception as e:
            content, coverage = f"[Image error: {e}]", "extraction failed"
        return content, None, coverage

    elif ext == ".eml":
        try:
            import email
            from email import policy as email_policy
            with open(file_path, encoding="utf-8", errors="replace") as f:
                msg = email.message_from_file(f, policy=email_policy.default)
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = (part.get_content() or "")[:300]
                        break
            else:
                body = (msg.get_content() or "")[:300]
            content  = (f"From: {msg.get('From', '')}\nSubject: {msg.get('Subject', '')}\n"
                        f"Date: {msg.get('Date', '')}\nBody: {body.strip()}")
            coverage = "headers + body excerpt (300 chars)"
        except Exception as e:
            content, coverage = f"[EML error: {e}]", "extraction failed"
        return content, None, coverage

    elif ext == ".msg":
        return "[MSG binary — Outlook message, filename signals only]", None, "binary, no extraction"

    elif ext == ".zip":
        try:
            import zipfile, tempfile
            from collections import Counter
            with zipfile.ZipFile(file_path) as z:
                names = z.namelist()
            exts        = Counter(Path(n).suffix.lower() for n in names if Path(n).suffix)
            ext_summary = ", ".join(f"{e}×{c}" for e, c in exts.most_common(5))
            top_names   = ", ".join(names[:8])
            header      = f"[ZIP: {len(names)} files | types: {ext_summary} | samples: {top_names}]"
            PRIORITY_EXTS = [".pdf", ".docx", ".txt", ".xlsx", ".pptx", ".csv",
                             ".json", ".ifc", ".dxf", ".eml"]
            candidates = [n for n in names if Path(n).suffix.lower() in PRIORITY_EXTS
                          and not n.endswith("/") and Path(n).suffix.lower() != ".zip"]
            candidates.sort(key=lambda n: PRIORITY_EXTS.index(Path(n).suffix.lower()))
            to_sample     = candidates[:2]
            sampled_parts = []
            if to_sample:
                with zipfile.ZipFile(file_path) as z:
                    with tempfile.TemporaryDirectory() as tmp:
                        for name in to_sample:
                            z.extract(name, tmp)
                            extracted   = Path(tmp) / name
                            sub_content, _, sub_cov = _extract_content(extracted)
                            sampled_parts.append(
                                f"[sampled: {Path(name).name} | {sub_cov}]\n{sub_content}")
            content  = header + ("\n\n" + "\n\n".join(sampled_parts) if sampled_parts else "")
            content  = content[:DEFAULT_MAX_CHARS * 3]
            coverage = (f"{len(names)} files in archive"
                        + (f" — {len(to_sample)} file(s) content-sampled" if to_sample
                           else " — no text files to sample"))
        except Exception as e:
            content, coverage = f"[ZIP error: {e}]", "extraction failed"
        return content, None, coverage

    elif ext in (".shp", ".geojson", ".kml"):
        try:
            raw      = file_path.read_text(encoding="utf-8", errors="replace")
            content  = raw[:400]
            coverage = _cov_chars(raw, 400, ext.upper())
        except Exception:
            size_kb  = file_path.stat().st_size // 1024
            content  = f"[{ext.upper()} spatial file — {size_kb} KB — likely binary SHP]"
            coverage = "binary, no extraction"
        return content, None, coverage

    return "", None, "unsupported format"


# ── Public API ────────────────────────────────────────────────────────────
def layer1_technical(file_path: Path) -> dict:
    ext                      = file_path.suffix.lower()
    content, pages, coverage = _extract_content(file_path)
    year                     = _extract_year(file_path.name, content)
    info_type                = INFO_TYPE_MAP.get(ext, "Unknown")
    size_kb                  = file_path.stat().st_size // 1024
    is_data_hint             = _is_data_hint(file_path, content)

    return {
        "filename":            file_path.name,
        "format":              ext.lstrip(".").upper(),
        "information_type":    info_type,
        "year":                year,
        "page_count":          pages,
        "size_kb":             size_kb,
        "folder":              file_path.parent.name,
        "file_path":           str(file_path),
        "content_sample":      content,
        "extraction_coverage": coverage,
        "is_data_hint":        is_data_hint,
    }
