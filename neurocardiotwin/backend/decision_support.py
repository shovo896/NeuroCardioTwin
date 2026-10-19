"""Private RAG-backed research decision support.

This module intentionally sends no raw waveforms, email addresses, or Auth0
identifiers to third-party providers.  It accepts only a small, server-built
summary of an already-completed local ONNX model result.
"""
from __future__ import annotations

import logging
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
LOGGER = logging.getLogger(__name__)


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
        # ``:fastest`` is a routing shorthand, not part of a Hub model ID.
        # InferenceClient expects the canonical model ID in its ``model``
        # parameter, so accepting the suffix here keeps an older Vercel value
        # from disabling the entire decision-support path.
        chat_model = os.getenv("HF_CHAT_MODEL", "Qwen/Qwen2.5-7B-Instruct").strip() or "Qwen/Qwen2.5-7B-Instruct"
        if chat_model.endswith(":fastest"):
            chat_model = chat_model.removesuffix(":fastest")
        # Gemma requires a separately accepted gated-model licence.  A fresh
        # provider token commonly has no such grant, which must not disable
        # the RAG path.  Qwen is provider-routable without that extra gate.
        if chat_model.lower().startswith("google/gemma"):
            chat_model = "Qwen/Qwen2.5-7B-Instruct"
        return cls(
            hf_token=os.getenv("HF_INFERENCE_TOKEN", "").strip(),
            pinecone_key=os.getenv("PINECONE_API_KEY", "").strip(),
            pinecone_host=os.getenv("PINECONE_INDEX_HOST", "").strip().removeprefix("https://").rstrip("/"),
            hf_chat_model=chat_model,
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


def _local_sources(limit: int = 3) -> list[dict[str, str]]:
    """Use reviewed local documents as a bounded continuity fallback.

    This keeps the user-facing research output available when a hosted
    embedding/chat provider or Pinecone is temporarily unavailable.  It never
    indexes or exposes user data and is deliberately limited to the approved
    project knowledge bundled with the server.
    """
    return [
        {"id": doc["id"], "title": doc["title"], "excerpt": doc["text"][:700]}
        for doc in _source_documents()[:limit]
    ]


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

    def _clients(self) -> tuple[InferenceClient, InferenceClient, Any]:
        if not self.ready:
            raise HTTPException(503, "AI decision support is not configured.")
        # Provider selection remains automatic: it permits a conversational
        # provider for chat while selecting a feature-extraction provider for
        # the embedding model.  No provider credentials reach the browser.
        # BGE is available from the first-party HF inference provider.  Pin
        # embeddings to it rather than relying on an automatic provider that
        # may only offer conversational models at request time.
        embedding_hf = InferenceClient(api_key=self.config.hf_token, provider="hf-inference", timeout=25)
        chat_hf = InferenceClient(api_key=self.config.hf_token, timeout=25)
        client = Pinecone(api_key=self.config.pinecone_key)
        host = self.config.pinecone_host
        # Pinecone's console shows both an index name and a data-plane host.
        # Resolve a bare index name so a harmless configuration mix-up does not
        # make all user decisions fail.
        if "." not in host:
            details = client.describe_index(host)
            host = details.get("host", "") if isinstance(details, dict) else getattr(details, "host", "")
        if not isinstance(host, str) or not host:
            raise RuntimeError("Pinecone index host could not be resolved.")
        index = client.Index(host=host)
        return embedding_hf, chat_hf, index

    def _embed(self, hf: InferenceClient, text: str) -> list[float]:
        return _as_vector(hf.feature_extraction(text, model=self.config.hf_embedding_model))

    def reindex(self) -> dict[str, Any]:
        """Index the reviewed project knowledge.  This is admin-only at the route."""
        embedding_hf, _, index = self._clients()
        docs = _source_documents()
        vectors = []
        for doc in docs:
            vectors.append({
                "id": doc["id"],
                "values": self._embed(embedding_hf, doc["text"]),
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

    @staticmethod
    def _retrieval_guided_decision(summary: dict[str, Any], sources: list[dict[str, str]]) -> str:
        """Keep a retrieval-grounded research response available if a chat
        provider is temporarily unavailable.  The user still receives one
        unified local-model + approved-knowledge result, never a diagnosis.
        """
        if summary["analysis_type"] == "seizure":
            result = "Local EEG model flagged a research pattern" if summary.get("detected") else "Local EEG model did not flag a research pattern"
        elif summary["analysis_type"] == "arrhythmia":
            result = f"Local ECG model returned {summary.get('classification', 'an unlabelled rhythm result')}"
        else:
            result = f"Local forecasting model prepared a {summary.get('forecast_horizon', 0)}-sample research forecast"
        source_names = ", ".join(f"[{source['title']}]" for source in sources[:2])
        return (
            f"• {result}; treat it as a prototype research output, not a clinical conclusion.\n"
            f"• Follow the approved validation workflow and inspect input quality before any further research use. {source_names}\n"
            "• If a clinical concern exists, use an appropriate qualified-clinician workflow rather than this interface."
        )

    def decide(self, summary: dict[str, Any]) -> dict[str, Any]:
        query = (
            f"NeuroCardioTwin research workflow for {summary['analysis_type']} model output. "
            f"Validated samples: {summary['input_quality']['valid_samples']}. "
            "Return only research workflow context and safe next validation steps."
        )
        try:
            embedding_hf, chat_hf, index = self._clients()
            sources = self._retrieve(embedding_hf, index, query)
        except RuntimeError as exc:
            if "No approved knowledge was retrieved" in str(exc):
                try:
                    # First-use bootstrap: only reviewed local knowledge is
                    # upserted; no user data or waveform is ever indexed.
                    self.reindex()
                    sources = self._retrieve(embedding_hf, index, query)
                except Exception as retry_exc:
                    LOGGER.warning("RAG bootstrap unavailable; using local approved knowledge (%s).", type(retry_exc).__name__)
                    sources = _local_sources()
            else:
                LOGGER.warning("RAG retrieval unavailable; using local approved knowledge (%s).", type(exc).__name__)
                sources = _local_sources()
        except Exception as exc:
            LOGGER.warning("RAG provider unavailable; using local approved knowledge (%s).", type(exc).__name__)
            sources = _local_sources()
            return {
                "decision": self._retrieval_guided_decision(summary, sources),
                "sources": sources,
                "safety_notice": SAFETY_NOTICE,
                "prototype": True,
            }
        evidence = "\n\n".join(f"[{source['title']}]\n{source['excerpt']}" for source in sources)
        system = (
            "You are a research decision-support assistant for NeuroCardioTwin. "
            "Use only the supplied evidence and model summary. Never diagnose, triage, prescribe, "
            "or claim clinical certainty. State that this is a prototype/research output. "
            "Give at most three concise validation-oriented bullet points and cite source titles in brackets."
        )
        user = f"MODEL SUMMARY (no raw signal):\n{summary}\n\nAPPROVED EVIDENCE:\n{evidence}"
        try:
            completion = chat_hf.chat_completion(
                model=self.config.hf_chat_model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                max_tokens=260,
                temperature=0.1,
            )
            choices = getattr(completion, "choices", None)
            content = getattr(getattr(choices[0], "message", None), "content", None) if choices else None
            if not isinstance(content, str) or not content.strip():
                raise RuntimeError("Hugging Face returned an empty decision-support response.")
        except Exception as exc:
            # Avoid exposing provider internals to the user.  Retrieval has
            # already succeeded, so a bounded evidence-guided decision remains
            # safer and more useful than failing the complete analysis.
            LOGGER.warning("Chat generation unavailable; using retrieval-guided decision (%s).", type(exc).__name__)
            content = self._retrieval_guided_decision(summary, sources)
        return {"decision": content.strip()[:2400], "sources": sources, "safety_notice": SAFETY_NOTICE, "prototype": True}

    @staticmethod
    def _chat_fallback(language: str, sources: list[dict[str, str]]) -> str:
        citations = " ".join(f"[{source['title']}]" for source in sources[:2])
        if language == "bn":
            return (
                "আমি অনুমোদিত গবেষণা-জ্ঞানভিত্তিক সহকারী। মডেলের ফলাফল ব্যাখ্যা, "
                "signal validation, বা গবেষণার পরের ধাপ সম্পর্কে প্রশ্ন করতে পারেন। "
                f"এটি চিকিৎসা নির্ণয় বা চিকিৎসা পরামর্শ নয়। {citations}"
            )
        return (
            "I can help explain model outputs, signal validation, and research workflow "
            "from the approved knowledge base. This is not a diagnosis or medical advice. "
            f"{citations}"
        )

    def chat(self, message: Any, language: Any = "en") -> dict[str, Any]:
        """Answer a short authenticated workspace question using approved RAG data.

        Conversations are intentionally not persisted.  The request never adds
        profile fields, raw signal arrays, uploads, or history to the prompt.
        """
        if not isinstance(message, str) or not (question := message.strip()):
            raise HTTPException(422, "Enter a question for the assistant.")
        if len(question) > 800:
            raise HTTPException(422, "Keep the question under 800 characters.")
        selected_language = "bn" if str(language).lower() in {"bn", "bangla", "bengali"} else "en"
        try:
            embedding_hf, chat_hf, index = self._clients()
            sources = self._retrieve(embedding_hf, index, question)
        except Exception as exc:
            LOGGER.warning("Chat retrieval unavailable; using local approved knowledge (%s).", type(exc).__name__)
            sources = _local_sources()
            return {"answer": self._chat_fallback(selected_language, sources), "sources": sources, "language": selected_language, "prototype": True}

        evidence = "\n\n".join(f"[{source['title']}]\n{source['excerpt']}" for source in sources)
        language_instruction = "Reply in clear Bangla." if selected_language == "bn" else "Reply in clear English."
        system = (
            "You are NeuroCardioTwin's research assistant. Use only the approved evidence supplied. "
            "Do not diagnose, triage, prescribe, interpret an individual waveform, or claim clinical certainty. "
            "Keep the answer concise, research-oriented, and cite the supplied source titles in brackets. "
            + language_instruction
        )
        try:
            completion = chat_hf.chat_completion(
                model=self.config.hf_chat_model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": question}, {"role": "user", "content": f"APPROVED EVIDENCE:\n{evidence}"}],
                max_tokens=280,
                temperature=0.2,
            )
            choices = getattr(completion, "choices", None)
            answer = getattr(getattr(choices[0], "message", None), "content", None) if choices else None
            if not isinstance(answer, str) or not answer.strip():
                raise RuntimeError("Hugging Face returned an empty chat response.")
        except Exception as exc:
            LOGGER.warning("Chat generation unavailable; using approved-knowledge reply (%s).", type(exc).__name__)
            answer = self._chat_fallback(selected_language, sources)
        return {"answer": answer.strip()[:2400], "sources": sources, "language": selected_language, "prototype": True}
