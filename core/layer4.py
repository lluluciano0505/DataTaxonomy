"""Layer 4 — Query-driven evidence retrieval and answer synthesis.

Given a user question, Layer 4:
1. Builds a search plan from the question
2. Ranks candidate files from processed CSV rows
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

_STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "into", "about", "where",
    "what", "which", "when", "does", "have", "there", "their", "your", "our", "should",
    "would", "could", "using", "used", "use", "find", "look", "need", "question",
    "project", "file", "files", "document", "documents", "data", "layer", "query",
}


SEARCH_PLAN_PROMPT = """\
You help search an urban-design project archive.
Given a user question, produce a compact search plan for retrieving relevant files.

Return ONLY JSON with this shape:
{
  "intent": "<short sentence>",
  "search_terms": ["<keywords and phrases, bilingual if useful>"],
  "domain_hints": ["<likely domain names>"],
  "asset_hints": ["<likely asset types>"],
  "lifecycle_hints": ["<likely lifecycle stages>"],
  "answer_type": "fact|location|comparison|recommendation|list|unknown"
}

Rules:
- Keep search_terms concise and retrieval-oriented.
- Include both the original language and likely English project-archive terms when useful.
- Domain hints must be from likely archive taxonomy such as Landscape & Public Realm, Urban Planning & Massing, Architecture & Buildings, Environment & Climate, Mobility & Transport, Administrative & Legal, Project Management, Reference & Research.
- Asset hints should be values like Data, Document, Drawing, Media, Archive.
- lifecycle_hints can be empty.
- If unsure, return broad but useful hints instead of inventing specifics.

Question: {question}
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


def _tokenize(text: str) -> list[str]:
    text = (text or "").lower()
    latin_tokens = re.findall(r"[a-z0-9][a-z0-9\-_]{1,}", text)
    phrase_tokens = re.findall(r"[\u4e00-\u9fff]{2,}", text)
    tokens = []
    for token in latin_tokens + phrase_tokens:
        if token not in _STOPWORDS and token not in tokens:
            tokens.append(token)
    return tokens


def build_search_plan(question: str, client: OpenAI, model: str) -> dict:
    """Use the LLM to derive retrieval hints from the user question."""
    fallback = {
        "intent": question.strip(),
        "search_terms": _tokenize(question)[:8],
        "domain_hints": [],
        "asset_hints": [],
        "lifecycle_hints": [],
        "answer_type": "unknown",
    }

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Respond only with valid JSON."},
                {"role": "user", "content": SEARCH_PLAN_PROMPT.format(question=question.strip())},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or ""
        plan = _safe_json_loads(raw, fallback)
    except Exception:
        plan = fallback

    plan.setdefault("intent", question.strip())
    plan.setdefault("search_terms", fallback["search_terms"])
    plan.setdefault("domain_hints", [])
    plan.setdefault("asset_hints", [])
    plan.setdefault("lifecycle_hints", [])
    plan.setdefault("answer_type", "unknown")
    return plan


def _score_text_match(text: str, search_terms: list[str], weight: float) -> float:
    hay = (text or "").lower()
    score = 0.0
    for term in search_terms:
        needle = str(term or "").strip().lower()
        if not needle:
            continue
        if needle in hay:
            score += weight
    return score


def rank_candidate_rows(df: pd.DataFrame, plan: dict, top_k: int = 8) -> pd.DataFrame:
    """Score processed rows by query relevance using metadata and summaries."""
    if df.empty:
        return df.copy()

    ranked = df.copy()
    search_terms = [str(x) for x in plan.get("search_terms", []) if str(x).strip()]
    domain_hints = {str(x).strip().lower() for x in plan.get("domain_hints", []) if str(x).strip()}
    asset_hints = {str(x).strip().lower() for x in plan.get("asset_hints", []) if str(x).strip()}
    lifecycle_hints = {str(x).strip().lower() for x in plan.get("lifecycle_hints", []) if str(x).strip()}

    scores: list[float] = []
    for _, row in ranked.iterrows():
        score = 0.0
        score += _score_text_match(str(row.get("filename", "")), search_terms, 4.0)
        score += _score_text_match(str(row.get("short_summary", "")), search_terms, 3.5)
        score += _score_text_match(str(row.get("review_reasons", "")), search_terms, 3.0)
        score += _score_text_match(str(row.get("file_path", "")), search_terms, 2.5)
        score += _score_text_match(str(row.get("domain", "")), search_terms, 2.0)
        score += _score_text_match(str(row.get("lifecycle", "")), search_terms, 1.5)
        score += _score_text_match(str(row.get("asset_type", "")), search_terms, 1.5)
        score += _score_text_match(str(row.get("format", "")), search_terms, 1.0)

        if str(row.get("domain", "")).strip().lower() in domain_hints:
            score += 5.0
        if str(row.get("asset_type", "")).strip().lower() in asset_hints:
            score += 3.0
        if str(row.get("lifecycle", "")).strip().lower() in lifecycle_hints:
            score += 2.5

        review_priority = str(row.get("review_priority", "")).strip().lower()
        if review_priority in {"critical", "urgent", "high"}:
            score += 0.5

        confidence = str(row.get("confidence", "")).strip().lower()
        if confidence == "high":
            score += 0.5
        elif confidence == "medium":
            score += 0.2

        scores.append(score)

    ranked["_query_score"] = scores
    ranked = ranked.sort_values(["_query_score", "confidence", "year"], ascending=[False, False, False], na_position="last")

    positive = ranked[ranked["_query_score"] > 0].head(top_k)
    if not positive.empty:
        return positive
    return ranked.head(min(top_k, len(ranked)))


def reread_candidate_files(candidates: pd.DataFrame, max_files: int = 6) -> list[dict[str, Any]]:
    """Re-read the most relevant files from disk using Layer 1 extraction."""
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
            reread = layer1_technical(file_path)
            reread_docs.append({
                "filename": reread.get("filename", file_path.name),
                "file_path": reread.get("file_path", str(file_path)),
                "domain": row.get("domain", "Unknown"),
                "asset_type": row.get("asset_type", "Unknown"),
                "lifecycle": row.get("lifecycle", "Unknown"),
                "summary": row.get("short_summary", ""),
                "coverage": reread.get("extraction_coverage", ""),
                "content_sample": reread.get("content_sample", "")[:2200],
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

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Respond only with valid JSON."},
                {
                    "role": "user",
                    "content": ANSWER_PROMPT.format(
                        question=question.strip(),
                        candidate_context=_build_candidate_context(reread_docs),
                    ),
                },
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        raw = resp.choices[0].message.content or ""
        answer = _safe_json_loads(raw, fallback)
    except Exception:
        answer = fallback

    answer.setdefault("answer", fallback["answer"])
    answer.setdefault("confidence", "Low")
    answer.setdefault("gaps", "")
    answer.setdefault("relevant_files", fallback_files)
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

    plan = build_search_plan(question, client=client, model=model)
    candidates = rank_candidate_rows(processed_df, plan=plan, top_k=top_k)
    reread_docs = reread_candidate_files(candidates, max_files=reread_k)
    answer = synthesize_query_answer(question, reread_docs, client=client, model=model)

    return {
        "question": question,
        "search_plan": plan,
        "answer": answer.get("answer", ""),
        "confidence": answer.get("confidence", "Low"),
        "gaps": answer.get("gaps", ""),
        "relevant_files": answer.get("relevant_files", []),
        "candidate_count": int(len(candidates)),
        "candidates": candidates[[c for c in [
            "filename", "file_path", "domain", "asset_type", "lifecycle", "short_summary", "_query_score"
        ] if c in candidates.columns]].to_dict("records"),
    }
