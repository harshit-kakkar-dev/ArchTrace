# 🏛️ ArchTrace — Recovering Unwritten Architectural Decisions

**ArchTrace** mines public engineering discussions (GitHub Issues, Pull Requests, and Discourse forums), extracts architectural decisions alongside **rejected alternatives and verifiable source citations**, links them to **rename-resilient code paths and AST symbols**, and automatically surfaces relevant history when new Pull Requests touch that code.

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