"""Layer 4 — Query-driven evidence retrieval and answer synthesis.

Given a user question, Layer 4:
1. Uses LLM semantic judgement to binary-screen candidate files
2. Selects the most relevant files for deeper reading
3. Re-reads the most relevant files from disk
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


BINARY_RELEVANCE_PROMPT = """\
You are screening archive files for a user question.
Decide relevance using semantic understanding, not keyword overlap.

Return ONLY JSON with this shape:
{
    "decisions": [
        {
            "file_path": "<full path exactly as provided>",
            "relevant": true,
            "confidence": 0.0,
            "reason": "<short reason>"
        }
    ]
}

Rules:
- Evaluate each file independently by meaning and likely evidence value.
- Mark relevant=true only if the file is likely useful for answering the question.
- confidence is 0.0 to 1.0.
- Keep reason concise (max 15 words).
- Do not invent file paths.

Question:
{question}

Files:
{batch_preview}
"""


BATCH_ROUTER_PROMPT = """\
You are selecting which archive batches are worth deeper inspection.
Each batch card summarizes a subset of files.

Return ONLY JSON with this shape:
{
    "selected_batch_ids": [0, 1, 2],
    "reason": "<one short sentence>"
}

Rules:
- Select 1 to {max_batches} batch ids.
- Choose only batches likely to contain evidence for the question.
- Use semantic meaning, not literal keyword matching.
- Do not invent batch ids.

Question:
{question}

Batch cards:
{batch_cards}
"""


ANSWER_PROMPT = """\
You answer questions about a design-project archive using ONLY the provided candidate files.
If the evidence is insufficient, say so clearly.

Return ONLY JSON with this shape:
{
  "answer": "<clear answer in the user's language if possible>",
  "confidence": "High|Medium|Low",
  "gaps": "<what is still uncertain or missing>",
  "relevant_files": [
    {
      "filename": "<file name>",
      "file_path": "<full path>",
      "why_it_matters": "<one sentence>",
      "evidence": "<short quote or extracted snippet>"
    }
  ]
}

Rules:
- Base the answer ONLY on the candidate files below.
- Prefer direct evidence over speculation.
- If the question asks "where", extract place/location clues.
- If the question asks for suitability/recommendation, explain what the documents support, and where evidence is weak.
- Keep `gaps` strictly in English (never Chinese), even if the answer is in another language.
- Keep the answer concise but useful.
- Include 2-6 relevant files when available.

User question:
{question}

Candidate files:
{candidate_context}
"""


def _safe_json_loads(raw: str, fallback: dict) -> dict:
    try:
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.IGNORECASE)
        return json.loads(cleaned)
    except Exception:
        return fallback


def _build_binary_batch_preview(batch: pd.DataFrame) -> str:
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


def _build_batch_cards(df: pd.DataFrame, batch_size: int = 30) -> tuple[list[pd.DataFrame], str]:
    """Build coarse batch cards for LLM routing before file-level relevance checks."""
    batches: list[pd.DataFrame] = []
    cards: list[str] = []
    for batch_id, start in enumerate(range(0, len(df), max(1, batch_size))):
        batch = df.iloc[start:start + max(1, batch_size)].copy()
        batches.append(batch)

        domains = ", ".join(batch.get("domain", pd.Series(dtype=str)).dropna().astype(str).value_counts().head(4).index.tolist())
        lifecycle = ", ".join(batch.get("lifecycle", pd.Series(dtype=str)).dropna().astype(str).value_counts().head(4).index.tolist())
        assets = ", ".join(batch.get("asset_type", pd.Series(dtype=str)).dropna().astype(str).value_counts().head(4).index.tolist())
        sample_files = ", ".join(batch.get("filename", pd.Series(dtype=str)).dropna().astype(str).head(6).tolist())
        sample_summaries = " | ".join(batch.get("short_summary", pd.Series(dtype=str)).dropna().astype(str).head(3).tolist())

        cards.append(
            f"[Batch {batch_id}]\n"
            f"File count: {len(batch)}\n"
            f"Top domains: {domains or 'Unknown'}\n"
            f"Top lifecycle: {lifecycle or 'Unknown'}\n"
            f"Top asset types: {assets or 'Unknown'}\n"
            f"Sample filenames: {sample_files or 'None'}\n"
            f"Sample summaries: {sample_summaries or 'None'}\n"
        )

    return batches, "\n\n".join(cards)


def _route_relevant_batches(
    question: str,
    batch_cards: str,
    client: OpenAI,
    model: str,
    max_batches: int,
    total_batches: int,
) -> list[int]:
    """Use LLM to pick promising batch ids for detailed relevance screening."""
    if total_batches <= max_batches:
        return list(range(total_batches))

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Respond only with valid JSON."},
                {
                    "role": "user",
                    "content": BATCH_ROUTER_PROMPT.format(
                        question=question.strip(),
                        batch_cards=batch_cards,
                        max_batches=max_batches,
                    ),
                },
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or ""
        parsed = _safe_json_loads(raw, {})
        selected = [int(x) for x in parsed.get("selected_batch_ids", []) if str(x).strip().isdigit()]
        selected = [x for x in selected if 0 <= x < total_batches]
        if selected:
            # preserve order + uniqueness
            unique = []
            for x in selected:
                if x not in unique:
                    unique.append(x)
            return unique[:max_batches]
    except Exception:
        pass

    # Fallback to first few batches when routing fails
    return list(range(min(max_batches, total_batches)))


def rank_candidate_rows(
    df: pd.DataFrame,
    question: str,
    client: OpenAI,
    model: str,
    top_k: int = 24,
    batch_size: int = 30,
    max_batches: int = 4,
) -> pd.DataFrame:
    """Non-exhaustive LLM retrieval: route to likely batches, then binary relevance within those batches."""
    if df.empty:
        return df.copy()

    ranked = df.copy().reset_index(drop=True)
    batches, batch_cards = _build_batch_cards(ranked, batch_size=batch_size)
    selected_batch_ids = _route_relevant_batches(
        question=question,
        batch_cards=batch_cards,
        client=client,
        model=model,
        max_batches=max_batches,
        total_batches=len(batches),
    )

    selected_df = pd.concat([batches[i] for i in selected_batch_ids], ignore_index=True) if selected_batch_ids else ranked.head(min(top_k, len(ranked))).copy()

    relevance_score = pd.Series([0.0] * len(selected_df), index=selected_df.index, dtype="float")
    is_relevant = pd.Series([False] * len(selected_df), index=selected_df.index, dtype="bool")

    for start in range(0, len(selected_df), max(1, batch_size)):
        batch = selected_df.iloc[start:start + max(1, batch_size)]
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "Respond only with valid JSON."},
                    {
                        "role": "user",
                        "content": BINARY_RELEVANCE_PROMPT.format(
                            question=question.strip(),
                            batch_preview=_build_binary_batch_preview(batch),
                        ),
                    },
                ],
                temperature=0,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content or ""
            parsed = _safe_json_loads(raw, {})
            decisions = parsed.get("decisions", [])

            by_path = {
                str(item.get("file_path", "")).strip(): item
                for item in decisions
                if str(item.get("file_path", "")).strip()
            }
            for idx, row in batch.iterrows():
                path_key = str(row.get("file_path", "")).strip()
                dec = by_path.get(path_key)
                if not dec:
                    continue
                rel = bool(dec.get("relevant", False))
                conf_raw = dec.get("confidence", 0.5)
                try:
                    conf = max(0.0, min(1.0, float(conf_raw)))
                except Exception:
                    conf = 0.5
                is_relevant.loc[idx] = rel
                relevance_score.loc[idx] = conf if rel else 0.0
        except Exception:
            continue

    selected_df["_query_score"] = relevance_score
    relevant_rows = selected_df[is_relevant].copy()
    if not relevant_rows.empty:
        relevant_rows = relevant_rows.sort_values(
            ["_query_score", "confidence", "year"],
            ascending=[False, False, False],
            na_position="last",
        )
        return relevant_rows.head(top_k)

    # Fallback: no clear relevant rows returned; keep best-confidence rows for next LLM stage
    selected_df = selected_df.sort_values(["confidence", "year"], ascending=[False, False], na_position="last")
    selected_df["_query_score"] = 0.0
    return selected_df.head(min(top_k, len(selected_df)))


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
    """Ask the LLM to answer using only the re-read candidate documents."""
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

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Respond only with valid JSON."},
                {
                    "role": "user",
                    "content": ANSWER_PROMPT.format(
                        question=question.strip(),
                        candidate_context=_build_candidate_context(docs_for_prompt),
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
