"""Evaluate the real configured local model on synthetic examples only.

This is separate from automated software tests, which use injected substitutes.
No model accuracy is claimed until this script is run against a real model.
"""

import argparse
import json
import os
from pathlib import Path
import time

from prs.ai_integration.providers import OllamaProvider
from prs.ai_integration.service import CategorizationService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=0, help="Limit cases; default runs all")
    args = parser.parse_args()
    cases = json.loads((Path(__file__).parent / "tests" / "synthetic_ai_cases.json").read_text())
    if args.limit > 0:
        cases = cases[:args.limit]
    provider = OllamaProvider(os.environ.get("PRS_OLLAMA_MODEL", "qwen2.5:3b"),
                              os.environ.get("PRS_OLLAMA_URL", "http://127.0.0.1:11434"))
    service = CategorizationService(provider)
    counts = {"correct": 0, "suggested": 0, "uncertain": 0, "timeout": 0, "unavailable": 0}
    for index, case in enumerate(cases, 1):
        start = time.perf_counter()
        result = service.request(str(index), case["note"], "synthetic-evaluator", 0)
        predicted = result.suggestion.category.value if result.suggestion else None
        correct = (predicted == case["expected"] if case["expected"] is not None else result.status == "uncertain")
        counts[result.status] += 1
        counts["correct"] += int(correct)
        print(json.dumps({"case": index, "expected": case["expected"], "predicted": predicted,
                          "status": result.status, "correct": correct,
                          "seconds": round(time.perf_counter() - start, 3)}))
    print(json.dumps({"model": provider.model, "cases": len(cases), **counts,
                      "suggestion_coverage": counts["suggested"] / len(cases),
                      "expected_outcome_match_rate": counts["correct"] / len(cases)}))
    if counts["unavailable"] + counts["timeout"] == len(cases):
        print("No usable model responses. Start Ollama, install/warm the configured model, and rerun.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
