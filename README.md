# ArchTrace
# 🏛️ ArchTrace — Recovering Unwritten Architectural Decisions

**ArchTrace** mines public engineering discussions (GitHub Issues, Pull Requests, and Discourse forums), extracts architectural decisions alongside **rejected alternatives and verifiable source citations**, links them to **rename-resilient code paths and AST symbols**, and automatically surfaces relevant history when new Pull Requests touch that code[cite: 9, 10].

---

## 🏗️ System Architecture

```text
┌──────────────────────┐   ┌──────────────────────────┐
│ GitHub Issues & PRs  │   │ Discourse (.json API)    │
└──────────┬───────────┘   └────────────┬─────────────┘
           └──────────────┬─────────────┘
                          ▼
         ┌─────────────────────────────────┐
         │ Incremental Sync & Identity     │  <-- SHA-256 content hashes +
         │ Resolver (`ingestion.py`,       │      cross-platform handle/name matching
         │ `identity.py`)                  │
         └────────────────┬────────────────┘
                          ▼
         ┌─────────────────────────────────┐
         │ Open-Weight Decision Extractor  │  <-- Llama 3.1 8B (Groq / OpenRouter)
         │ (`extractor.py`)                │      extracts Decisions, Rejected Ideas,
         └────────────────┬────────────────┘      Verbatim Quotes & Post URLs
                          ▼
         ┌─────────────────────────────────┐
         │ Rename-Resilient Knowledge DB   │  <-- SQLite + `git log --diff-filter=R`
         │ & Episodic PR Memory            │      + Python `ast` symbol matching
         └────────────────┬────────────────┘
                          ▼
         ┌─────────────────────────────────┐
         │ GitHub Action PR Bot & UI       │  <-- Comments on PRs + learns from
         │ (`pr_bot.py`, `app.py`)         │      `/archtrace helpful|obsolete`
         └─────────────────────────────────┘
```

---

## 🧠 Design Questions & Engineering Trade-Offs

1. **Connecting the same person across platforms (`src/archtrace/identity.py`)**[cite: 9]
   - **Approach:** Deterministic normalization + tiered similarity matching (exact email/handle = `1.0`, normalized display name = `0.92`, fuzzy `SequenceMatcher >= 0.84`)[cite: 9].
   - **Trade-off:** High precision without requiring private OAuth tokens; avoids false merges on short common usernames by enforcing an `0.84` threshold.
2. **Incremental updates without reprocessing (`src/archtrace/ingestion.py`)**[cite: 9]
   - **Approach:** Every post is fingerprinted with a `SHA-256` hash in SQLite (`ingested_posts`)[cite: 9]. Unchanged comments are skipped in $O(1)$ lookup time.
   - **Trade-off:** Edited posts automatically trigger re-extraction because their SHA-256 digest changes, while unchanged threads incur zero LLM token cost.
3. **Surviving file moves and renames (`src/archtrace/git_tracker.py`)**[cite: 9]
   - **Approach:** Automatically parses `git log --diff-filter=R --summary` to build a transitive rename graph (`old_path <-> new_path`), paired with Python `ast` symbol extraction on PR diffs[cite: 9, 10].
   - **Trade-off:** Using Python's `ast` module avoids false positives from comments/docstrings while gracefully falling back to token scanning on partial diff hunks.
4. **Verifiable provenance over blind trust (`src/archtrace/extractor.py`)**[cite: 9]
   - **Approach:** Every extracted decision and rejected idea stores the direct post URL and verbatim quote from the original author[cite: 9].
5. **Self-improving PR memory (`src/archtrace/git_tracker.py`)**[cite: 10]
   - **Approach:** Maintainer feedback (`/archtrace helpful` or `/archtrace obsolete`) is stored in `pr_feedback_memory`, dynamically suppressing outdated decisions on future PRs[cite: 10].

---

## 🚀 Quickstart

```bash
# 1. Create virtual environment & install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. (Optional) Configure free open-weight LLM key (Groq / OpenRouter)
export LLM_API_KEY="gsk_your_free_groq_key"

# 3. Run automated tests
pytest -v

# 4. Launch the interactive dashboard
streamlit run app.py
```
