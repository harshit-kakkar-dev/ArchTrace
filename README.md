Markdown
# 🧭 ArchTrace

**Institutional Memory & Unwritten Decision Recovery for Open Source**

ArchTrace extracts the architectural decisions, rejected alternatives, and engineering rationale buried across GitHub Issues, Pull Requests, Discourse forums, and public mailing list archives. It links each recovered decision to the exact source files and AST symbols it governs—surviving file moves and renames—and automatically guards new Pull Requests with self-improving episodic memory.

---

## ✨ Key Capabilities

1. **Multi-Source Discussion Ingestion (`src/archtrace/ingestion.py`)**
   - Ingests public discussions from **GitHub Issues & Pull Requests** (both single threads and batch repository scans), **Discourse forums** (`discuss.python.org`), and **Public Mailing List Archives** (`mail.python.org` Pipermail `.txt` and HTML).
   - Uses **SHA-256 content hashing** (`processed_posts` table) to skip unchanged posts during incremental updates rather than reprocessing entire repositories.

2. **Open-Weight Decision & Rejected-Alternative Extraction (`src/archtrace/extractor.py`)**
   - Extracts structured JSON containing the **chosen decision**, **rationale**, **rejected alternatives**, **author handles**, **verbatim quotes**, and **affected files/symbols**.
   - Auto-discovers active open-weight models via Groq or OpenRouter (`openai/gpt-oss-120b`, Llama 3.3, Qwen) and falls back cleanly to an offline heuristic extractor when no API key is configured.

3. **Rename-Resilient Code Linking & AST Symbol Tracking (`src/archtrace/git_tracker.py`)**
   - Tracks file moves and renames transitively via `git log --diff-filter=R` (`file_renames` table) so historical decisions remain attached even after refactoring.
   - Parses Python diffs using the built-in `ast` module to match modified functions, classes, and attributes against stored decision symbols.

4. **Cross-Platform Contributor Identity Resolution (`src/archtrace/identity.py`)**
   - Unifies contributors across GitHub, Discourse, and mailing lists using email matching, handle normalization, and display-name fuzzy similarity.

5. **Automated GitHub Action PR Guardian & Episodic Memory (`src/archtrace/pr_bot.py`)**
   - Runs automatically on Pull Requests via `.github/workflows/archtrace-pr-bot.yml` to warn contributors when a diff touches code or symbols tied to previously rejected approaches, complete with verbatim quotes and clickable source URLs.
   - Supports maintainer feedback commands (`/archtrace helpful` and `/archtrace obsolete`) stored in `pr_feedback_memory` to reinforce valid rules and suppress outdated alerts.

6. **Blind PEP Evaluation Benchmark (`src/archtrace/benchmarks.py`)**
   - Evaluates decision recovery against Python Enhancement Proposals (**PEP 678** and **PEP 851**) by feeding only the raw discussion thread while withholding the official PEP document—achieving **100.0% blind rejected-idea recall** on PEP 678.

---

## 🏗️ Project Architecture

```text
ArchTrace/
├── app.py                                   # Streamlit Contributor Explorer, Repo Indexer, PR Simulator & Benchmark UI
├── src/archtrace/
│   ├── __init__.py
│   ├── db.py                                # SQLite schema, decision deduplication & episodic PR feedback memory
│   ├── identity.py                          # Cross-platform contributor identity resolution
│   ├── ingestion.py                         # GitHub REST, Discourse JSON & Pipermail archive connectors + SHA-256 sync
│   ├── extractor.py                         # Auto-discovering open-weight LLM extractor + offline heuristic fallback
│   ├── git_tracker.py                       # Transitive Git rename lineage, AST symbol analysis & ranked keyword search
│   ├── pr_bot.py                            # Automated PR diff analyzer & GitHub comment formatter
│   └── benchmarks.py                        # Blind PEP 678 & PEP 851 evaluation suite and recall scorer
├── tests/
│   └── test_archtrace.py                    # Pytest suite covering identity, incremental hashing & rename resilience
├── .github/workflows/archtrace-pr-bot.yml   # GitHub Actions CI workflow for automated PR decision checks
└── requirements.txt
```

# 🚀 Quickstart

1. Clone & Install Dependencies
Bash
git clone [https://github.com/harshit-kakkar-dev/ArchTrace.git](https://github.com/harshit-kakkar-dev/ArchTrace.git)
cd ArchTrace
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

3. Configure Optional Open-Weight LLM API Key
Create a .env file in the project root (optional—ArchTrace works out of the box in offline heuristic mode without a key):

Code snippet
LLM_API_KEY=your_groq_or_openrouter_api_key 

3. Launch the Web Dashboard
Bash
streamlit run app.py
Open http://localhost:8501 to explore:

# 🧭 Contributor Explorer: 
Natural-language & symbol search, codebase decision hotspots, side-by-side Chosen vs. Rejected briefs, and one-click ADR (.md) export.

# 📥 Index Repository: 
Batch-scan public GitHub repos or extract decisions from single GitHub Issues/PRs, Discourse threads, or mailing list archives.

# 🤖 PR Guardian & Team: 
Simulate rename-aware PR checks, record episodic feedback, and inspect unified cross-platform contributor identities.

# 🧪 Blind Benchmark: 
Run blind rejected-idea recall tests on Python PEPs.

# 🧪 Running Automated Tests
Bash
source venv/bin/activate
python -m pytest -v
