"""Private RAG-backed research decision support.

This module intentionally sends no raw waveforms, email addresses, or Auth0
identifiers to third-party providers.  It accepts only a small, server-built
summary of an already-completed local ONNX model result.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from huggingface_hub import InferenceClient
from pinecone import Pinecone


ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_DIR = ROOT / "knowledge"
SAFETY_NOTICE = (
    "Research decision support only; not a diagnosis, triage, treatment, or "
    "medical-device output. Escalate clinical concerns to a qualified clinician."
)


@dataclass(frozen=True)
class DecisionConfig:
    hf_token: str
    pinecone_key: str
    pinecone_host: str
    hf_chat_model: str
    hf_embedding_model: str
    namespace: str

    @classmethod
    def from_environment(cls) -> "DecisionConfig":
        return cls(
            hf_token=os.getenv("HF_INFERENCE_TOKEN", "").strip(),
            pinecone_key=os.getenv("PINECONE_API_KEY", "").strip(),
            pinecone_host=os.getenv("PINECONE_INDEX_HOST", "").strip().removeprefix("https://").rstrip("/"),
            hf_chat_model=os.getenv("HF_CHAT_MODEL", "google/gemma-2-2b-it:fastest").strip(),
            hf_embedding_model=os.getenv("HF_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5").strip(),
            namespace=os.getenv("PINECONE_NAMESPACE", "neurocardiotwin-knowledge-v1").strip() or "neurocardiotwin-knowledge-v1",
        )

    @property
    def ready(self) -> bool:
        return bool(self.hf_token and self.pinecone_key and self.pinecone_host)


def _as_vector(value: Any) -> list[float]:
    if hasattr(value, "tolist"):
        value = value.tolist()
    # Some embedding runtimes return [[...]] for a single input.
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], list):
        value = value[0]
    if not isinstance(value, list) or not value or not all(isinstance(item, (int, float)) for item in value):
        raise RuntimeError("Hugging Face returned an invalid embedding.")
    return [float(item) for item in value]


def _source_documents() -> list[dict[str, str]]:
    documents: list[dict[str, str]] = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        text = path.read_text(encoding="utf-8").strip()
        if text:
            documents.append({"id": path.stem, "title": path.stem.replace("-", " ").title(), "text": text})
    if not documents:
        raise RuntimeError("No approved local RAG knowledge documents are available.")
    return documents


def compact_analysis(analysis_type: str, model_result: dict[str, Any]) -> dict[str, Any]:
    """Whitelist a model summary so waveform arrays can never cross the boundary."""
    if analysis_type not in {"seizure", "arrhythmia", "forecast"}:
        raise HTTPException(422, "Unsupported analysis type.")
    quality = model_result.get("input_quality") if isinstance(model_result.get("input_quality"), dict) else {}
    clean: dict[str, Any] = {
        "analysis_type": analysis_type,
        "session_id": str(model_result.get("session_id", "local"))[:80],
        "input_quality": {
            "status": str(quality.get("status", "Unknown"))[:40],
            "valid_samples": int(quality.get("valid_samples", 0) or 0),
            "finite_ratio": float(quality.get("finite_ratio", 0) or 0),
        },
    }
    try:
        if analysis_type == "seizure":
            clean.update({
                "detected": bool(model_result.get("detected", False)),
                "probability": round(float(model_result.get("probability", 0)), 5),
                "threshold": round(float(model_result.get("threshold", 0.5)), 5),
            })
        elif analysis_type == "arrhythmia":
            clean.update({
                "classification": str(model_result.get("classification", "Unknown"))[:80],
                "confidence": round(float(model_result.get("confidence", 0)), 5),
                "abnormal_probability": round(float(model_result.get("abnormal_probability", 0)), 5),
            })
        else:
            clean["forecast_horizon"] = int(model_result.get("forecast_horizon", 0) or 0)
    except (TypeError, ValueError):
        raise HTTPException(422, "Model-result summary contains invalid values.") from None
    return clean


class RAGDecisionService:
    def __init__(self, config: DecisionConfig | None = None) -> None:
        self.config = config or DecisionConfig.from_environment()

    @property
    def ready(self) -> bool:
        return self.config.ready

    def _clients(self) -> tuple[InferenceClient, Any]:
        if not self.ready:
            raise HTTPException(503, "AI decision support is not configured.")
        hf = InferenceClient(provider="hf-inference", api_key=self.config.hf_token)
        index = Pinecone(api_key=self.config.pinecone_key).Index(host=self.config.pinecone_host)
        return hf, index

    def _embed(self, hf: InferenceClient, text: str) -> list[float]:
        return _as_vector(hf.feature_extraction(text, model=self.config.hf_embedding_model))

    def reindex(self) -> dict[str, Any]:
        """Index the reviewed project knowledge.  This is admin-only at the route."""
        hf, index = self._clients()
        docs = _source_documents()
        vectors = []
        for doc in docs:
            vectors.append({
                "id": doc["id"],
                "values": self._embed(hf, doc["text"]),
                "metadata": {"title": doc["title"], "text": doc["text"][:3500], "source_id": doc["id"]},
            })
        index.upsert(vectors=vectors, namespace=self.config.namespace)
        return {"indexed_documents": len(vectors), "namespace": self.config.namespace}

    def _retrieve(self, hf: InferenceClient, index: Any, query: str) -> list[dict[str, str]]:
        response = index.query(vector=self._embed(hf, query), top_k=3, include_metadata=True, namespace=self.config.namespace)
        matches = response.get("matches", []) if isinstance(response, dict) else getattr(response, "matches", [])
        sources: list[dict[str, str]] = []
        for match in matches:
            metadata = match.get("metadata", {}) if isinstance(match, dict) else getattr(match, "metadata", {})
            if not isinstance(metadata, dict):
                continue
            text, title = metadata.get("text"), metadata.get("title")
            if isinstance(text, str) and isinstance(title, str):
                sources.append({"id": str(metadata.get("source_id", "knowledge")), "title": title[:120], "excerpt": text[:700]})
        if not sources:
            raise RuntimeError("No approved knowledge was retrieved. Reindex the knowledge base first.")
        return sources

    def decide(self, summary: dict[str, Any]) -> dict[str, Any]:
        hf, index = self._clients()
        query = (
            f"NeuroCardioTwin research workflow for {summary['analysis_type']} model output. "
            f"Validated samples: {summary['input_quality']['valid_samples']}. "
            "Return only research workflow context and safe next validation steps."
        )
        sources = self._retrieve(hf, index, query)
        evidence = "\n\n".join(f"[{source['title']}]\n{source['excerpt']}" for source in sources)
        system = (
            "You are a research decision-support assistant for NeuroCardioTwin. "
            "Use only the supplied evidence and model summary. Never diagnose, triage, prescribe, "
            "or claim clinical certainty. State that this is a prototype/research output. "
            "Give at most three concise validation-oriented bullet points and cite source titles in brackets."
        )
        user = f"MODEL SUMMARY (no raw signal):\n{summary}\n\nAPPROVED EVIDENCE:\n{evidence}"
        completion = hf.chat_completion(
            model=self.config.hf_chat_model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            max_tokens=260,
            temperature=0.1,
        )
        choices = getattr(completion, "choices", None)
        if not choices:
            raise RuntimeError("Hugging Face returned no decision-support response.")
        content = getattr(getattr(choices[0], "message", None), "content", None)
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Hugging Face returned an empty decision-support response.")
        return {"decision": content.strip()[:2400], "sources": sources, "safety_notice": SAFETY_NOTICE, "prototype": True}
