from typing import Dict, List

SAMPLE_PEP_BENCHMARKS: Dict[str, Dict] = {
    "PEP 678 – Enriching Exceptions with Notes (Discourse #12641)": {
        "pep_number": "PEP 678",
        "pep_url": "https://peps.python.org/pep-0678/",
        "discourse_url": "https://discuss.python.org/t/pep-678-enriching-exceptions-with-notes/12641",
        "ground_truth_rejected_ideas": [
            "An assignable __note__ or __notes__ string attribute directly on BaseException",
            "Augment the raise statement with new syntax like 'raise Exception() with note'",
            "Add a helper function in contextlib like contextlib.add_exc_note()",
            "Use print() or logging instead of attaching notes to exceptions",
            "raise Wrapper(explanation) from err (exception chaining destroys original exception type)",
            "Store notes only on ExceptionGroup rather than individual Exceptions",
        ],
        "expected_keywords": ["__note__", "with", "contextlib", "print", "wrapper", "exceptiongroup"],
        "synthetic_discussion_posts": [
            {
                "post_uid": "disc_678_1",
                "author": "Zac-HD",
                "canonical_id": "user_zachd",
                "created_at": "2021-12-20T10:00:00Z",
                "url": "https://discuss.python.org/t/pep-678-enriching-exceptions-with-notes/12641/1",
                "text": (
                    "In early drafts of PEP 678 affecting Objects/exceptions.c and Lib/traceback.py, we proposed "
                    "an assignable `__note__` attribute where users could set `err.__note__ = 'extra info'`. "
                    "However, when multiple libraries catch and annotate the same exception, a single assignable "
                    "`__note__` attribute gets overwritten unless callers manually concatenate strings. Moving to "
                    "`BaseException.add_note(note)` storing a list in `__notes__` prevents accidental overwrites."
                ),
            },
            {
                "post_uid": "disc_678_2",
                "author": "iritkatriel",
                "canonical_id": "user_iritkatriel",
                "created_at": "2021-12-21T14:22:00Z",
                "url": "https://discuss.python.org/t/pep-678-enriching-exceptions-with-notes/12641/8",
                "text": (
                    "Several people asked why not just use `raise Wrapper(explanation) from err` or `print()` / `logging`. "
                    "Wrapping changes the exception type, which breaks `except SpecificError:` clauses and makes "
                    "`ExceptionGroup.split()` unusable. Also, someone suggested new syntax like `raise Exception() with 'note'`, "
                    "or a helper `contextlib.add_exc_note()`, or storing notes only in `ExceptionGroup`. New language syntax "
                    "is way too heavy and doesn't help when an exception is mutated inside an `ExceptionGroup`."
                ),
            },
        ],
    },
    "PEP 851 – Add list.discard() (Discourse Thread)": {
        "pep_number": "PEP 851",
        "pep_url": "https://peps.python.org/pep-0851/",
        "discourse_url": "https://discuss.python.org/t/pep-851-add-list-discard/65000",
        "ground_truth_rejected_ideas": [
            "Adding a boolean parameter on list.remove() such as list.remove(x, missing_ok=True)",
            "Adding discard() to collections.abc.MutableSequence",
            "Adding deque.discard() in the same proposal",
        ],
        "expected_keywords": ["missing_ok", "mutablesequence", "deque"],
        "synthetic_discussion_posts": [
            {
                "post_uid": "disc_851_1",
                "author": "coredev_list",
                "canonical_id": "user_coredevlist",
                "created_at": "2026-10-15T09:15:00Z",
                "url": "https://discuss.python.org/t/pep-851-add-list-discard/65000/2",
                "text": (
                    "When editing Objects/listobject.c, we considered adding a parameter on `list.remove(x, missing_ok=True)` "
                    "instead of a new `list.discard(x)` method. That was rejected because boolean flag parameters hurt readability "
                    "at the call site, and `set.discard()` already establishes the exact method name in Python. We also rejected "
                    "adding `discard()` to `collections.abc.MutableSequence` because that would force every third-party subclass "
                    "to implement it, and deferred `deque.discard()` to keep the change minimal."
                ),
            }
        ],
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