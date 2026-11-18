import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "src"))

from archtrace.benchmarks import SAMPLE_PEP_BENCHMARKS, compute_blind_recall
from archtrace.db import init_db
from archtrace.extractor import extract_decisions_from_posts
from archtrace.git_tracker import (
    extract_python_ast_symbols,
    query_decisions_for_pr,
    record_pr_feedback,
    register_file_rename,
)
from archtrace.identity import IdentityResolver
from archtrace.ingestion import filter_new_or_updated_posts


def test_cross_platform_identity_resolution(tmp_path):
    db_file = str(tmp_path / "test.db")
    init_db(db_file)

    cid1 = IdentityResolver.resolve("discourse", "Zac-HD", "Zac Hatfield-Dodds", db_path=db_file)
    cid2 = IdentityResolver.resolve("github", "Zac-HD", "Zac Hatfield-Dodds", db_path=db_file)
    assert cid1 == cid2


def test_incremental_post_hashing(tmp_path):
    db_file = str(tmp_path / "test.db")
    init_db(db_file)

    posts = [
        {"post_uid": "p1", "canonical_id": "u1", "created_at": "2026-01-01", "text": "Initial proposal"},
        {"post_uid": "p2", "canonical_id": "u2", "created_at": "2026-01-02", "text": "Rejected due to O(n^2)"},
    ]
    new_1, skip_1 = filter_new_or_updated_posts("https://example.com/t/1", posts, db_path=db_file)
    assert len(new_1) == 2
    assert skip_1 == 0

    new_2, skip_2 = filter_new_or_updated_posts("https://example.com/t/1", posts, db_path=db_file)
    assert len(new_2) == 0
    assert skip_2 == 2


def test_rename_resilience_ast_and_episodic_memory(tmp_path):
    db_file = str(tmp_path / "test.db")
    init_db(db_file)

    bench = SAMPLE_PEP_BENCHMARKS["PEP 678 – Enriching Exceptions with Notes (Discourse #12641)"]
    extracted = extract_decisions_from_posts(
        bench["discourse_url"],
        bench["synthetic_discussion_posts"],
        provider="Offline Heuristic Mode",
        db_path=db_file,
    )
    recall = compute_blind_recall(extracted["rejected_alternatives"], bench["expected_keywords"])
    assert recall["recall_percent"] >= 50.0

    # Simulate file rename from Objects/exceptions.c -> src/core/exception_types.c
    register_file_rename("Objects/exceptions.c", "src/core/exception_types.c", db_path=db_file)
    diff_snippet = "+ def set_err():\n+     err.__note__ = 'oops'\n"
    syms = extract_python_ast_symbols(diff_snippet)
    assert "__note__" in syms

    matches = query_decisions_for_pr("src/core/exception_types.c", diff_snippet, db_path=db_file)
    assert len(matches) == 1
    assert any("Rename-resilient" in r for r in matches[0]["matched_reasons"])

    # Mark decision obsolete via self-improving PR memory -> should no longer alert
    record_pr_feedback(matches[0]["id"], "PR-99", "OBSOLETE", "Superseded", db_path=db_file)
    matches_after = query_decisions_for_pr("src/core/exception_types.c", diff_snippet, db_path=db_file)
    assert len(matches_after) == 0