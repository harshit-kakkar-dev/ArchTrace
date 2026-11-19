import json
from pathlib import Path
from typing import Dict, List

CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "real_discourse_cache.json"


def _load_real_cached_posts(key: str) -> List[Dict]:
    if CACHE_PATH.exists():
        data = json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        return data.get(key, {}).get("posts", [])
    return []


SAMPLE_PEP_BENCHMARKS: Dict[str, Dict] = {
    "PEP 678 – Enriching Exceptions with Notes (Discourse #13374)": {
        "pep_number": "PEP 678",
        "pep_url": "https://peps.python.org/pep-0678/",
        "discourse_url": "https://discuss.python.org/t/pep-678-enriching-exceptions-with-notes/13374",
        "ground_truth_rejected_ideas": [
            "An assignable __note__ or __notes__ string attribute directly on BaseException",
            "Augment the raise statement with new syntax like 'raise Exception() with note'",
            "Add a helper function in contextlib like contextlib.add_exc_note()",
            "Use print() or logging instead of attaching notes to exceptions",
            "raise Wrapper(explanation) from err (exception chaining destroys original exception type)",
            "Store notes only on ExceptionGroup rather than individual Exceptions",
        ],
        "expected_keywords": ["__note__", "with", "contextlib", "print", "wrapper", "exceptiongroup"],
        "cached_real_posts": _load_real_cached_posts("PEP 678"),
    },
    "PEP 703 – Making the Global Interpreter Lock Optional (Discourse #22606)": {
        "pep_number": "PEP 703",
        "pep_url": "https://peps.python.org/pep-0703/",
        "discourse_url": "https://discuss.python.org/t/pep-703-making-the-global-interpreter-lock-optional/22606",
        "ground_truth_rejected_ideas": [
            "Runtime toggle to enable/disable the GIL within a single interpreter build",
            "Keeping the GIL permanently without a --disable-gil build configuration",
            "Subinterpreters alone as a complete replacement for shared-memory multi-threading",
        ],
        "expected_keywords": ["runtime", "gil", "subinterpreter", "flag", "build"],
        "cached_real_posts": _load_real_cached_posts("PEP 703"),
    },
}


def compute_blind_recall(extracted_alternatives: List[Dict], expected_keywords: List[str]) -> Dict:
    """Computes how many ground-truth rejected ideas from the hidden PEP were recovered."""
    combined_text = " ".join(
        f"{alt.get('idea', '')} {alt.get('reason_rejected', '')} {alt.get('verbatim_quote', '')}".lower()
        for alt in extracted_alternatives
    )
    matched = [kw for kw in expected_keywords if kw.lower() in combined_text]
    total = len(expected_keywords)
    recall_pct = round((len(matched) / total) * 100, 1) if total else 100.0
    return {
        "matched_count": len(matched),
        "total_ground_truth": total,
        "recall_percent": recall_pct,
        "matched_keywords": matched,
    }
