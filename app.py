import os
import sys
from pathlib import Path
import streamlit as st
from dotenv import load_dotenv

# Ensure src/ is importable when running `streamlit run app.py`
ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from archtrace.benchmarks import SAMPLE_PEP_BENCHMARKS, compute_blind_recall
from archtrace.db import DEFAULT_DB_PATH, get_connection, init_db
from archtrace.extractor import extract_decisions_from_posts
from archtrace.git_tracker import (
    query_decisions_for_pr,
    record_pr_feedback,
    register_file_rename,
    sync_git_renames,
)
from archtrace.git_tracker import (
    query_decisions_for_pr,
    record_pr_feedback,
    register_file_rename,
    search_decisions,
    sync_git_renames,
)
from archtrace.identity import IdentityResolver
from archtrace.ingestion import (
    fetch_discourse_thread,
    fetch_github_discussion,
    fetch_github_repo_threads,
    filter_new_or_updated_posts,
)
load_dotenv()
st.set_page_config(page_title="ArchTrace — Architectural Decision Recovery", layout="wide")
init_db()

st.title("🏛️ ArchTrace: Institutional Memory & Unwritten Decision Recovery")
st.caption(
    "Extracts architectural decisions & rejected alternatives from GitHub Issues, PRs, and Discourse forums, "
    "tracks file renames via Git history, and guards Pull Requests with self-improving memory."
)

# Sidebar Configuration
with st.sidebar:
    st.header("⚙️ Open-Weight Model Settings")
    provider = st.selectbox(
        "LLM Provider (Open-Weight Prioritized)",
        [
            "Groq (Free Open-Weight - Llama 3.1 8B)",
            "OpenRouter (Free Open-Weight)",
            "Offline Heuristic Mode (No API Key)",
        ],
    )
    default_key = os.getenv("LLM_API_KEY", "")
    api_key = ""
    if "Offline" not in provider:
        api_key = st.text_input("Free API Key (Groq / OpenRouter)", value=default_key, type="password")
        st.caption("Leave blank to automatically use Offline Heuristic Fallback.")

    st.divider()
    st.markdown("### 📐 Architecture Highlights")
    st.markdown(
        "- **Blind PEP Recovery:** Extracts Rejected Ideas without seeing the PEP\n"
        "- **Incremental Sync:** SHA-256 post hashing skips unchanged comments\n"
        "- **Git Rename Resilience:** `git log --diff-filter=R` + AST symbol matching\n"
        "- **Self-Improving Memory:** PR feedback updates active vs. obsolete decisions"
    )

tab_search, tab1, tab2, tab3, tab4 = st.tabs([
    "🔎 1. Search Decisions (New Contributors)",
    "🧪 2. Blind PEP Benchmark",
    "🌐 3. Multi-Source Ingestion",
    "🤖 4. PR Bot & Episodic Memory",
    "🪪 5. Cross-Platform Identity",
])
with tab_search:
    st.subheader("🔎 Search Architectural Decisions Before Writing Code")
    st.write(
        "New to the codebase? Search by feature, rejected idea, file path (even renamed paths), "
        "or function/symbol name to see why things were built this way."
    )
    col_q1, col_q2 = st.columns([3, 1])
    with col_q1:
        search_query = st.text_input(
            "Search by keyword, file path, or symbol (leave empty to browse all stored decisions)",
            placeholder="e.g., __note__, missing_ok, Objects/exceptions.c, exception",
        )
    with col_q2:
        show_obsolete = st.checkbox("Include obsolete decisions", value=False)

    hits = search_decisions(search_query, include_obsolete=show_obsolete)
    st.caption(f"Showing **{len(hits)}** recorded architectural decision(s).")

    for item in hits:
        with st.expander(f"📌 #{item['id']} — {item['title']} [{item['status']}]", expanded=True):
            st.markdown(f"**Chosen Decision:** {item['final_decision']}")
            st.markdown(f"**Why It Won:** {item['rationale']}")
            st.markdown(f"**Files:** `{', '.join(item['affected_files']) or 'N/A'}` | **Symbols:** `{', '.join(item['affected_symbols']) or 'N/A'}`")
            st.markdown(f"**Original Thread:** [{item['source_url']}]({item['source_url']})")
            st.markdown("**❌ Rejected Alternatives (Do Not Re-Propose Without New Context):**")
            for alt in item["rejected_alternatives"]:
                st.markdown(
                    f"- **{alt.get('idea')}** — *{alt.get('reason_rejected')}* "
                    f"([Source]({alt.get('source_url')}) by `{alt.get('author')}`: *\"{alt.get('verbatim_quote')}\"*)"
                )
# =====================================================================
# TAB 1: BLIND PEP BENCHMARK
# =====================================================================
with tab1:
    st.subheader("Blind Decision Recovery on Python PEPs")
    st.write(
        "Feeds the discussion thread to ArchTrace **without access to the PEP**, extracts rejected alternatives, "
        "and computes recall against the official PEP `Rejected Ideas` section."
    )

    selected_pep = st.selectbox("Select Python PEP Benchmark", list(SAMPLE_PEP_BENCHMARKS.keys()))
    benchmark = SAMPLE_PEP_BENCHMARKS[selected_pep]

    col_left, col_right = st.columns([1.2, 1])
    with col_left:
        fetch_live = st.checkbox("Fetch live thread from discuss.python.org", value=False)
        if st.button("🚀 Run Blind Decision Recovery", type="primary"):
            with st.spinner("Analyzing discussion thread (PEP hidden)..."):
                try:
                    if fetch_live:
                        posts = fetch_discourse_thread(benchmark["discourse_url"], max_posts=25)
                    else:
                        posts = benchmark["synthetic_discussion_posts"]
                        for p in posts:
                            IdentityResolver.resolve("discourse", p["author"], p["author"])
                except Exception as exc:
                    st.warning(f"Live fetch unavailable ({exc}); using offline thread snapshot.")
                    posts = benchmark["synthetic_discussion_posts"]

                new_posts, skipped = filter_new_or_updated_posts(benchmark["discourse_url"], posts)
                st.info(f"Incremental Sync: **{len(new_posts)} new posts processed**, **{skipped} unchanged posts skipped**.")

                extracted = extract_decisions_from_posts(
                    benchmark["discourse_url"],
                    posts,
                    provider=provider,
                    api_key=api_key,
                )
                st.session_state["pep_result"] = extracted
                st.session_state["pep_benchmark"] = benchmark

    if "pep_result" in st.session_state:
        res = st.session_state["pep_result"]
        bench = st.session_state["pep_benchmark"]
        recall = compute_blind_recall(res.get("rejected_alternatives", []), bench["expected_keywords"])

        with col_left:
            st.success(f"### Extracted Decision: {res.get('title')}")
            st.caption(f"Engine: `{res.get('extraction_mode', 'Offline Heuristic Mode')}`")
            st.markdown(f"**Chosen Decision:** {res.get('final_decision')}")
            st.markdown(f"**Rationale:** {res.get('rationale')}")
            st.markdown(f"**Linked Files:** `{', '.join(res.get('affected_files', []))}`")
            st.markdown(f"**Linked AST Symbols:** `{', '.join(res.get('affected_symbols', []))}`")

            st.markdown("#### ❌ Recovered Rejected Alternatives (Verifiable Citations)")
            for idx, alt in enumerate(res.get("rejected_alternatives", []), 1):
                with st.expander(f"Rejected Idea #{idx}: {alt.get('idea')}", expanded=True):
                    st.markdown(f"- **Why Rejected:** {alt.get('reason_rejected')}")
                    st.markdown(f"- **Author:** `{alt.get('author')}`")
                    st.markdown(f"- **Direct Source:** [{alt.get('source_url')}]({alt.get('source_url')})")
                    st.info(f"**Verbatim Quote:** \"{alt.get('verbatim_quote')}\"")

        with col_right:
            st.metric(
                label="Blind Rejected-Idea Recall Score",
                value=f"{recall['recall_percent']}%",
                delta=f"{recall['matched_count']}/{recall['total_ground_truth']} ground-truth ideas recovered",
            )
            st.warning(f"### 🔑 Hidden Answer Key ({bench['pep_number']} 'Rejected Ideas')")
            st.caption(f"Official PEP (Withheld from LLM): {bench['pep_url']}")
            for item in bench["ground_truth_rejected_ideas"]:
                st.markdown(f"- ✅ **{item}**")

# =====================================================================
# TAB 2: LIVE MULTI-SOURCE INGESTION
# =====================================================================
with tab2:
    st.subheader("Ingest Any Public GitHub Repository, Issue/PR, or Discourse Thread")
    source_type = st.radio(
        "Ingestion Mode",
        ["Batch-Index Any GitHub Repository (owner/repo)", "Single GitHub Issue / PR", "Discourse Forum Thread"],
        horizontal=True,
    )

    if "Batch-Index" in source_type:
        repo_slug = st.text_input("Public GitHub Repository (`owner/repo`)", value="pallets/flask")
        max_threads = st.slider("Top Discussed Closed Issues/PRs to Index", min_value=2, max_value=12, value=5)

        if st.button("🚀 Batch-Index Repository Decisions", type="primary"):
            with st.spinner(f"Scanning top discussed issues & PRs in {repo_slug}..."):
                try:
                    threads = fetch_github_repo_threads(repo_slug, max_threads=max_threads)
                    total_new, total_skipped = 0, 0
                    extracted_list = []

                    for t in threads:
                        new_p, skip_p = filter_new_or_updated_posts(t["url"], t["posts"])
                        total_new += len(new_p)
                        total_skipped += skip_p
                        if new_p or skip_p:
                            dec = extract_decisions_from_posts(
                                t["url"],
                                t["posts"],
                                provider=provider,
                                api_key=api_key,
                            )
                            extracted_list.append((t, dec))

                    st.success(
                        f"Indexed **{len(extracted_list)} threads** from `{repo_slug}`! "
                        f"(Incremental Sync: **{total_new} new posts processed**, **{total_skipped} unchanged skipped**)"
                    )
                    for t, dec in extracted_list:
                        with st.expander(f"#{t['number']} — {dec.get('title', t['title'])}", expanded=False):
                            st.markdown(f"- **Source:** [{t['url']}]({t['url']})")
                            st.markdown(f"- **Decision:** {dec.get('final_decision')}")
                            st.markdown(f"- **Linked Files:** `{', '.join(dec.get('affected_files', []))}`")
                            for alt in dec.get("rejected_alternatives", [])[:3]:
                                st.markdown(f"  - ❌ **{alt.get('idea')}** (*\"{alt.get('verbatim_quote')}\"*)")
                except Exception as exc:
                    st.error(f"Repository indexing failed: {exc}")
    else:
        default_url = (
            "https://github.com/pallets/flask/issues/4612"
            if "GitHub" in source_type
            else "https://discuss.python.org/t/pep-678-enriching-exceptions-with-notes/12641"
        )
        url_input = st.text_input("Public Thread URL", value=default_url)
        files_input = st.text_input("Optional File Path Tags (comma-separated)", value="")
        symbols_input = st.text_input("Optional Symbol Tags (comma-separated)", value="")

        if st.button("📥 Ingest & Extract Decisions"):
            with st.spinner("Fetching discussion and running incremental filter..."):
                try:
                    posts = (
                        fetch_github_discussion(url_input)
                        if "GitHub" in source_type
                        else fetch_discourse_thread(url_input)
                    )
                    new_posts, skipped = filter_new_or_updated_posts(url_input, posts)
                    st.info(f"Incremental Sync: **{len(new_posts)} new**, **{skipped} skipped**.")

                    files_list = [f.strip() for f in files_input.split(",") if f.strip()]
                    syms_list = [s.strip() for s in symbols_input.split(",") if s.strip()]
                    out = extract_decisions_from_posts(
                        url_input,
                        posts,
                        provider=provider,
                        api_key=api_key,
                        target_files=files_list,
                        target_symbols=syms_list,
                    )
                    st.success("Stored decision in ArchTrace institutional memory!")
                    st.json(out)
                except Exception as exc:
                    st.error(f"Ingestion failed: {exc}")
# =====================================================================
# TAB 3: PR MEMORY BOT & SELF-IMPROVING EPISODIC MEMORY
# =====================================================================
with tab3:
    st.subheader("🤖 Pull Request Memory Bot & Git Rename Lineage")

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("#### 1. File Move / Rename Tracking")
        if st.button("🔄 Auto-Scan Local Git History (`git log --diff-filter=R`)"):
            detected = sync_git_renames(".")
            st.success(f"Scanned repository git history: {detected} rename(s) synced.")

        old_p = st.text_input("Historical File Path", value="Objects/exceptions.c")
        new_p = st.text_input("Renamed File Path", value="src/core/exception_types.c")
        if st.button("🔗 Register Rename Link"):
            register_file_rename(old_p, new_p)
            st.success(f"Linked `{old_p}` ➡️ `{new_p}`")

    with col_b:
        st.markdown("#### 2. Simulate Incoming Pull Request")
        pr_file = st.text_input("Modified File in PR", value="src/core/exception_types.c")
        pr_diff = st.text_area(
            "PR Code Diff",
            value=(
                "@@ -42,3 +42,5 @@\n"
                "+ def attach_note(err):\n"
                "+     err.__note__ = 'retry failed'\n"
            ),
            height=130,
        )

    if st.button("🔍 Run PR Decision Check", type="primary"):
        matches = query_decisions_for_pr(pr_file, pr_diff)
        st.session_state["pr_matches"] = matches
        if not matches:
            st.warning("No matching active decisions found. Run Tab 1 first to seed decisions!")

    for m in st.session_state.get("pr_matches", []):
        st.markdown("---")
        st.markdown(f"### 🤖 GitHub PR Bot Comment Preview — Decision #{m['id']}")
        st.info(
            f"**🏛️ ArchTrace Institutional Memory Alert**\n\n"
            f"- **Decision:** {m['title']} (Helpful confirmations: `{m['helpful_votes']}`)\n"
            f"- **Trigger Reason:** {', '.join(m['matched_reasons'])}\n"
            f"- **Chosen Approach:** {m['final_decision']}\n"
            f"- **Rationale:** {m['rationale']}"
        )
        for alt in m["rejected_alternatives"]:
            st.markdown(
                f"- ❌ **Rejected:** {alt.get('idea')} — *{alt.get('reason_rejected')}* "
                f"([Source]({alt.get('source_url')}) by `{alt.get('author')}`: *\"{alt.get('verbatim_quote')}\"*)"
            )

        fb_col1, fb_col2 = st.columns(2)
        with fb_col1:
            if st.button(f"👍 /archtrace helpful (#{m['id']})", key=f"help_{m['id']}"):
                record_pr_feedback(m["id"], "PR-DEMO", "HELPFUL", "Maintainer confirmed warning is valid.")
                st.success("Episodic memory updated: decision reinforced!")
        with fb_col2:
            if st.button(f"🗑️ /archtrace obsolete (#{m['id']})", key=f"obs_{m['id']}"):
                record_pr_feedback(m["id"], "PR-DEMO", "OBSOLETE", "Decision superseded by newer architecture.")
                st.warning("Episodic memory updated: decision marked OBSOLETE and suppressed on future PRs!")

# =====================================================================
# TAB 4: CROSS-PLATFORM IDENTITY RESOLUTION
# =====================================================================
with tab4:
    st.subheader("🪪 Contributor Identity Resolution Across Platforms")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        plat = st.selectbox("Platform", ["github", "discourse", "mailing_list"])
    with c2:
        handle = st.text_input("Handle", value="Zac-HD")
    with c3:
        d_name = st.text_input("Display Name", value="Zac Hatfield-Dodds")
    with c4:
        email = st.text_input("Email (Optional)", value="")

    if st.button("Resolve Identity"):
        cid = IdentityResolver.resolve(plat, handle, d_name, email)
        st.success(f"Resolved to Canonical Contributor ID: `{cid}`")

    conn = get_connection(DEFAULT_DB_PATH)
    rows = conn.execute("SELECT * FROM contributors").fetchall()
    conn.close()
    if rows:
        st.table([dict(r) for r in rows])