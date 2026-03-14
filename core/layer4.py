"""Layer 4 — Query-driven evidence retrieval and answer synthesis.

Given a user question, Layer 4:
1. Uses LLM to shortlist relevant files from CSV metadata
2. Re-reads shortlisted files from disk
3. Runs per-file LLM review
4. Produces an answer with supporting files and evidence
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd
from openai import OpenAI

from .layer1 import layer1_technical


SHORTLIST_PROMPT = """\
You shortlist files relevant to a user question from a metadata catalog.

Return ONLY JSON with this shape:
{{
    "selected_file_paths": ["<path1>", "<path2>"],
    "reason": "<short sentence>"
}}

Rules:
- Use semantic understanding (topic, intent, evidence value), not keyword counting.
- Select 0 to {max_select} files from this catalog chunk.
- Prefer files likely to directly answer the question.
- Do not invent file paths.

Question:
{question}

Catalog chunk:
{catalog_chunk}
"""


DOC_REVIEW_PROMPT = """\
You review ONE file for a user question.
Use semantic understanding of the content and metadata.

Return ONLY JSON with this shape:
{{
    "file_path": "<exact path>",
    "relevant": true,
    "relevance_confidence": 0.0,
    "why_it_matters": "<one short sentence>",
    "evidence": "<short quote/snippet>",
    "candidate_answer_fragment": "<what this file contributes>",
    "gaps": "<missing details in this file>"
}}

Rules:
- Decide relevance for this specific file only.
- If not relevant, set relevant=false and keep fields concise.
- Do not invent facts beyond provided content.

User question:
{question}

File payload:
{file_payload}
"""


AGGREGATE_ANSWER_PROMPT = """\
You synthesize a final answer from per-file review results.
Use ONLY the reviewed file evidence below.

Return ONLY JSON with this shape:
{{
    "answer": "<clear answer in the user's language if possible>",
    "confidence": "High|Medium|Low",
    "gaps": "<remaining uncertainty in English>",
    "relevant_files": [
        {{
            "filename": "<file name>",
            "file_path": "<full path>",
            "why_it_matters": "<one sentence>",
            "evidence": "<short quote/snippet>"
        }}
    ]
}}

Rules:
- Prefer direct evidence and reconcile contradictions explicitly.
- Keep `gaps` strictly in English.
- Include 2-6 files when possible.

User question:
{question}

Per-file reviews:
{reviews_context}
"""


def _safe_json_loads(raw: str, fallback: dict) -> dict:
    try:
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.IGNORECASE)
        return json.loads(cleaned)
    except Exception:
        return fallback


def _build_catalog_chunk(batch: pd.DataFrame) -> str:
    parts: list[str] = []
    for idx, (_, row) in enumerate(batch.iterrows(), start=1):
        parts.append(
            f"[File {idx}]\n"
            f"Filename: {row.get('filename', '')}\n"
            f"Path: {row.get('file_path', '')}\n"
            f"Domain: {row.get('domain', '')}\n"
            f"Asset Type: {row.get('asset_type', '')}\n"
            f"Lifecycle: {row.get('lifecycle', '')}\n"
            f"Summary: {str(row.get('short_summary', ''))[:220]}\n"
            f"Reasoning: {str(row.get('_reasoning', ''))[:220]}\n"
        )
    return "\n\n".join(parts)


def rank_candidate_rows(
    df: pd.DataFrame,
    question: str,
    client: OpenAI,
    model: str,
    top_k: int = 24,
    chunk_size: int = 80,
) -> pd.DataFrame:
    """Pure-LLM retrieval: shortlist directly from CSV metadata chunks."""
    if df.empty:
        return df.copy()

    ranked = df.copy().reset_index(drop=True)
    selected_paths: list[str] = []

    for start in range(0, len(ranked), max(1, chunk_size)):
        chunk = ranked.iloc[start:start + max(1, chunk_size)]
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Respond only with valid JSON."},
                    {
                        "role": "user",
                        "content": SHORTLIST_PROMPT.format(
                            question=question.strip(),
                            catalog_chunk=_build_catalog_chunk(chunk),
                            max_select=max(2, min(12, top_k)),
                        ),
                    },
                ],
                temperature=0,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content or ""
            parsed = _safe_json_loads(raw, {})
            picks = [str(x).strip() for x in parsed.get("selected_file_paths", []) if str(x).strip()]
            selected_paths.extend(picks)
        except Exception:
            continue

    # preserve order + uniqueness
    unique_paths: list[str] = []
    for p in selected_paths:
        if p not in unique_paths:
            unique_paths.append(p)

    if unique_paths:
        selected_df = ranked[ranked["file_path"].astype(str).isin(unique_paths)].copy()
        # keep LLM-selected order
        order_map = {p: i for i, p in enumerate(unique_paths)}
        selected_df["_llm_order"] = selected_df["file_path"].astype(str).map(order_map).fillna(999999)
        selected_df = selected_df.sort_values(["_llm_order", "confidence", "year"], ascending=[True, False, False], na_position="last")
        selected_df["_query_score"] = 1.0
        return selected_df.head(top_k)

    # Fallback when LLM returns no paths
    fallback = ranked.sort_values(["confidence", "year"], ascending=[False, False], na_position="last").head(min(top_k, len(ranked))).copy()
    fallback["_query_score"] = 0.0
    return fallback


def _read_full_file_content(file_path: Path, max_chars: int = 24000) -> tuple[str, str]:
    """Read a deeper/full content slice for query answering, beyond layer1 short samples."""
    ext = file_path.suffix.lower()

    try:
        if ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(str(file_path))
            parts: list[str] = []
            for page_idx, page in enumerate(reader.pages):
                text = (page.extract_text() or "").strip()
                if text:
                    parts.append(f"[p{page_idx + 1}] {text}")
                if sum(len(p) for p in parts) >= max_chars:
                    break
            raw = "\n".join(parts)
            return raw[:max_chars] or "[PDF has little or no extractable text]", f"fuller PDF pass across {min(len(reader.pages), page_idx + 1 if 'page_idx' in locals() else 0)} page(s)"

        if ext in {".docx", ".doc"}:
            import docx
            doc = docx.Document(str(file_path))
            parts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            for table in doc.tables:
                for row in table.rows:
                    row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                    if row_text:
                        parts.append(row_text)
                    if sum(len(p) for p in parts) >= max_chars:
                        break
            raw = "\n".join(parts)
            return raw[:max_chars] or "[Document has little extractable text]", "fuller DOCX pass"

        if ext == ".pptx":
            from pptx import Presentation
            prs = Presentation(str(file_path))
            parts: list[str] = []
            for i, slide in enumerate(prs.slides):
                texts = [shape.text.strip() for shape in slide.shapes if shape.has_text_frame and shape.text.strip()]
                if texts:
                    parts.append(f"[Slide {i+1}] " + " | ".join(texts))
                if sum(len(p) for p in parts) >= max_chars:
                    break
            raw = "\n".join(parts)
            return raw[:max_chars] or "[Presentation has little extractable text]", "fuller PPTX pass"

        if ext in {".txt", ".json"}:
            raw = file_path.read_text(encoding="utf-8", errors="replace")
            return raw[:max_chars], "full text read"

        if ext == ".csv":
            df = pd.read_csv(file_path, encoding="utf-8", errors="replace")
            raw = f"Columns: {list(df.columns)}\n{df.head(200).to_string()}"
            return raw[:max_chars], "CSV deeper tabular read"

        if ext in {".xlsx", ".xls"}:
            xl = pd.ExcelFile(str(file_path))
            blocks: list[str] = [f"Sheets: {xl.sheet_names}"]
            for sheet in xl.sheet_names[:5]:
                df = pd.read_excel(file_path, sheet_name=sheet, nrows=80)
                blocks.append(f"[Sheet: {sheet}]\nColumns: {list(df.columns)}\n{df.to_string()}")
                if sum(len(b) for b in blocks) >= max_chars:
                    break
            raw = "\n\n".join(blocks)
            return raw[:max_chars], "Excel deeper read"

        if ext == ".eml":
            import email
            from email import policy as email_policy
            with open(file_path, encoding="utf-8", errors="replace") as f:
                msg = email.message_from_file(f, policy=email_policy.default)
            body_parts = []
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body_parts.append(part.get_content() or "")
            else:
                body_parts.append(msg.get_content() or "")
            raw = f"From: {msg.get('From', '')}\nSubject: {msg.get('Subject', '')}\nDate: {msg.get('Date', '')}\n\n" + "\n".join(body_parts)
            return raw[:max_chars], "fuller email read"
    except Exception:
        pass

    fallback = layer1_technical(file_path)
    return str(fallback.get("content_sample", ""))[:max_chars], str(fallback.get("extraction_coverage", "layer1 fallback"))


def reread_candidate_files(candidates: pd.DataFrame, max_files: int = 6) -> list[dict[str, Any]]:
    """Re-read selected files from disk using deeper/full-content reads when possible."""
    reread_docs: list[dict[str, Any]] = []

    for _, row in candidates.head(max_files).iterrows():
        file_path = Path(str(row.get("file_path", ""))).expanduser()
        if not file_path.exists() or not file_path.is_file():
            reread_docs.append({
                "filename": str(row.get("filename", file_path.name or "Unknown")),
                "file_path": str(file_path),
                "domain": row.get("domain", "Unknown"),
                "asset_type": row.get("asset_type", "Unknown"),
                "lifecycle": row.get("lifecycle", "Unknown"),
                "summary": row.get("short_summary", ""),
                "coverage": "file missing at query time",
                "content_sample": "[File not found on disk during query reread]",
                "query_score": float(row.get("_query_score", 0)),
            })
            continue

        try:
            content_sample, coverage = _read_full_file_content(file_path)
            reread = layer1_technical(file_path)
            reread_docs.append({
                "filename": reread.get("filename", file_path.name),
                "file_path": reread.get("file_path", str(file_path)),
                "domain": row.get("domain", "Unknown"),
                "asset_type": row.get("asset_type", "Unknown"),
                "lifecycle": row.get("lifecycle", "Unknown"),
                "summary": row.get("short_summary", ""),
                "coverage": coverage or reread.get("extraction_coverage", ""),
                "content_sample": content_sample[:24000],
                "query_score": float(row.get("_query_score", 0)),
            })
        except Exception as exc:
            reread_docs.append({
                "filename": str(row.get("filename", file_path.name)),
                "file_path": str(file_path),
                "domain": row.get("domain", "Unknown"),
                "asset_type": row.get("asset_type", "Unknown"),
                "lifecycle": row.get("lifecycle", "Unknown"),
                "summary": row.get("short_summary", ""),
                "coverage": f"reread failed: {exc}",
                "content_sample": "[Could not re-read file content]",
                "query_score": float(row.get("_query_score", 0)),
            })

    return reread_docs


def _build_candidate_context(docs: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for idx, doc in enumerate(docs, start=1):
        parts.append(
            f"[Candidate {idx}]\n"
            f"Filename: {doc.get('filename', '')}\n"
            f"Path: {doc.get('file_path', '')}\n"
            f"Domain: {doc.get('domain', '')}\n"
            f"Asset Type: {doc.get('asset_type', '')}\n"
            f"Lifecycle: {doc.get('lifecycle', '')}\n"
            f"Query Score: {doc.get('query_score', 0):.1f}\n"
            f"Pipeline Summary: {doc.get('summary', '')}\n"
            f"Extraction Coverage: {doc.get('coverage', '')}\n"
            f"Content Sample:\n{doc.get('content_sample', '')}\n"
        )
    return "\n\n".join(parts)


def _build_single_file_payload(doc: dict[str, Any]) -> str:
    return (
        f"Filename: {doc.get('filename', '')}\n"
        f"Path: {doc.get('file_path', '')}\n"
        f"Domain: {doc.get('domain', '')}\n"
        f"Asset Type: {doc.get('asset_type', '')}\n"
        f"Lifecycle: {doc.get('lifecycle', '')}\n"
        f"Pipeline Summary: {doc.get('summary', '')}\n"
        f"Extraction Coverage: {doc.get('coverage', '')}\n"
        f"Content:\n{doc.get('content_sample', '')}\n"
    )


def _review_files_individually(
    question: str,
    docs: list[dict[str, Any]],
    client: OpenAI,
    model: str,
) -> list[dict[str, Any]]:
    """Run one LLM call per file so each file is read and judged independently."""
    reviews: list[dict[str, Any]] = []
    for doc in docs:
        fallback = {
            "file_path": doc.get("file_path", ""),
            "relevant": False,
            "relevance_confidence": 0.0,
            "why_it_matters": "Could not reliably parse this file review.",
            "evidence": str(doc.get("content_sample", ""))[:200],
            "candidate_answer_fragment": "",
            "gaps": "File-level review failed.",
        }
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Respond only with valid JSON."},
                    {
                        "role": "user",
                        "content": DOC_REVIEW_PROMPT.format(
                            question=question.strip(),
                            file_payload=_build_single_file_payload(doc),
                        ),
                    },
                ],
                temperature=0,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content or ""
            parsed = _safe_json_loads(raw, fallback)
            parsed.setdefault("file_path", doc.get("file_path", ""))
            parsed.setdefault("relevant", False)
            parsed.setdefault("relevance_confidence", 0.0)
            parsed.setdefault("why_it_matters", "")
            parsed.setdefault("evidence", "")
            parsed.setdefault("candidate_answer_fragment", "")
            parsed.setdefault("gaps", "")
            parsed["filename"] = doc.get("filename", "")
            reviews.append(parsed)
        except Exception as exc:
            fb = dict(fallback)
            fb["gaps"] = f"File-level review request failed: {exc}"
            fb["filename"] = doc.get("filename", "")
            reviews.append(fb)
    return reviews


def _build_reviews_context(reviews: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for i, r in enumerate(reviews, start=1):
        blocks.append(
            f"[Review {i}]\n"
            f"Filename: {r.get('filename', '')}\n"
            f"Path: {r.get('file_path', '')}\n"
            f"Relevant: {r.get('relevant', False)}\n"
            f"Relevance confidence: {r.get('relevance_confidence', 0.0)}\n"
            f"Why it matters: {r.get('why_it_matters', '')}\n"
            f"Evidence: {r.get('evidence', '')}\n"
            f"Answer fragment: {r.get('candidate_answer_fragment', '')}\n"
            f"File gaps: {r.get('gaps', '')}\n"
        )
    return "\n\n".join(blocks)


def _prepare_docs_for_synthesis(
    docs: list[dict[str, Any]],
    max_docs: int = 8,
    max_doc_chars: int = 6000,
    max_total_chars: int = 70000,
) -> list[dict[str, Any]]:
    """Bound context size so LLM synthesis does not fail from oversized prompts."""
    if not docs:
        return []

    ordered = sorted(docs, key=lambda d: float(d.get("query_score", 0.0)), reverse=True)
    selected: list[dict[str, Any]] = []
    used_chars = 0

    for doc in ordered[:max_docs * 2]:
        if len(selected) >= max_docs:
            break
        raw = str(doc.get("content_sample", ""))
        clipped = raw[:max_doc_chars]
        add_len = len(clipped)
        if selected and used_chars + add_len > max_total_chars:
            continue
        if not selected and add_len > max_total_chars:
            clipped = clipped[:max_total_chars]
            add_len = len(clipped)

        d2 = dict(doc)
        d2["content_sample"] = clipped
        selected.append(d2)
        used_chars += add_len

    return selected or [
        {
            **dict(ordered[0]),
            "content_sample": str(ordered[0].get("content_sample", ""))[: min(max_doc_chars, max_total_chars)],
        }
    ]


def synthesize_query_answer(question: str, reread_docs: list[dict[str, Any]], client: OpenAI, model: str) -> dict:
    """Two-step synthesis: per-file LLM review, then LLM aggregation."""
    fallback_files = [
        {
            "filename": doc.get("filename", ""),
            "file_path": doc.get("file_path", ""),
            "why_it_matters": doc.get("summary", "Potentially relevant file."),
            "evidence": str(doc.get("content_sample", ""))[:200],
        }
        for doc in reread_docs[:3]
    ]
    fallback = {
        "answer": "I could not generate a reliable answer from the available files.",
        "confidence": "Low",
        "gaps": "Layer 4 synthesis failed or the evidence was too weak.",
        "relevant_files": fallback_files,
    }

    if not reread_docs:
        return {
            "answer": "No candidate files were available for this question.",
            "confidence": "Low",
            "gaps": "No files matched the query strongly enough to analyze.",
            "relevant_files": [],
        }

    docs_for_prompt = _prepare_docs_for_synthesis(reread_docs)
    reviews = _review_files_individually(question, docs_for_prompt, client=client, model=model)
    relevant_reviews = [r for r in reviews if bool(r.get("relevant", False))]
    reviews_for_aggregate = relevant_reviews or reviews

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Respond only with valid JSON."},
                {
                    "role": "user",
                    "content": AGGREGATE_ANSWER_PROMPT.format(
                        question=question.strip(),
                        reviews_context=_build_reviews_context(reviews_for_aggregate),
                    ),
                },
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or ""
        answer = _safe_json_loads(raw, fallback)
    except Exception as exc:
        answer = fallback
        answer["gaps"] = f"Layer 4 synthesis request failed: {exc}"

    answer.setdefault("answer", fallback["answer"])
    answer.setdefault("confidence", "Low")
    answer.setdefault("gaps", "")
    answer.setdefault("relevant_files", fallback_files)
    if re.search(r"[\u4e00-\u9fff]", str(answer.get("gaps", ""))):
        answer["gaps"] = "Some uncertainty remains due to limited or conflicting evidence across the reviewed files."
    return answer


def layer4_query(
    question: str,
    processed_df: pd.DataFrame,
    client: OpenAI,
    model: str,
    top_k: int = 8,
    reread_k: int = 6,
) -> dict:
    """End-to-end Layer 4 question answering over processed archive results."""
    if processed_df is None or processed_df.empty:
        return {
            "question": question,
            "search_plan": {},
            "answer": "No processed files are available for querying.",
            "confidence": "Low",
            "gaps": "Run the pipeline first so Layer 4 has files to search.",
            "relevant_files": [],
            "candidate_count": 0,
        }

    plan = {
        "mode": "pure_llm_retrieval",
        "intent": question.strip(),
        "notes": "LLM batch routing + LLM binary relevance; no keyword/BM25 retrieval.",
    }
    candidates = rank_candidate_rows(
        processed_df,
        question=question,
        client=client,
        model=model,
        top_k=max(top_k, 10),
    )
    # Read all retrieved candidates (not a tiny subset) before synthesis.
    deep_read_candidates = candidates.copy()
    reread_docs = reread_candidate_files(deep_read_candidates, max_files=max(1, len(deep_read_candidates)))
    answer = synthesize_query_answer(question, reread_docs, client=client, model=model)

    return {
        "question": question,
        "search_plan": plan,
        "answer": answer.get("answer", ""),
        "confidence": answer.get("confidence", "Low"),
        "gaps": answer.get("gaps", ""),
        "relevant_files": answer.get("relevant_files", []),
        "candidate_count": int(len(candidates)),
        "deep_read_count": int(len(deep_read_candidates)),
        "candidates": candidates[[c for c in [
            "filename", "file_path", "domain", "asset_type", "lifecycle", "short_summary", "_query_score"
        ] if c in candidates.columns]].to_dict("records"),
    }
