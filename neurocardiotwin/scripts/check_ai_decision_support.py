"""Verify a configured RAG provider without printing any secret.

Run this only after setting fresh environment variables locally or in a secure
CI/Vercel context.  ``--live`` sends a compact synthetic summary; it never
sends a signal, an email address, an Auth0 subject or a token to providers.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Permit ``python scripts/check_ai_decision_support.py`` from the project root
# without requiring callers to modify PYTHONPATH.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.decision_support import DecisionConfig, RAGDecisionService, compact_analysis


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="Call configured providers with a synthetic summary.")
    parser.add_argument("--reindex", action="store_true", help="Upsert only reviewed local knowledge markdown files.")
    args = parser.parse_args()
    config = DecisionConfig.from_environment()
    print(f"provider configuration: {'ready' if config.ready else 'missing required server variables'}")
    print(f"chat model: {config.hf_chat_model}; embedding model: {config.hf_embedding_model}")
    print(f"index host configured: {'yes' if bool(config.pinecone_host) else 'no'}")
    if not config.ready:
        return 2
    service = RAGDecisionService(config)
    if args.reindex:
        indexed = service.reindex()
        print(f"knowledge reindex: {indexed['indexed_documents']} approved document(s)")
    if args.live:
        summary = compact_analysis("seizure", {
            "session_id": "provider-smoke-test",
            "detected": False,
            "probability": 0.12,
            "threshold": 0.5,
            "input_quality": {"status": "Validated", "valid_samples": 128, "finite_ratio": 1.0},
        })
        result = service.decide(summary)
        print(f"decision response: {len(result['decision'])} characters; sources: {len(result['sources'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
