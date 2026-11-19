import os
import re
import sys
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from archtrace.benchmarks import SAMPLE_PEP_BENCHMARKS, compute_blind_recall
from archtrace.db import DEFAULT_DB_PATH, get_connection, init_db
from archtrace.extractor import extract_decisions_from_posts
from archtrace.git_tracker import (
    get_decision_stats,
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
    fetch_mailing_list_archive,
    filter_new_or_updated_posts,
)
from archtrace.pr_bot import format_pr_comment
from archtrace.ui import (
    inject_console_css,
    render_app_header,
    render_decision_record,
    render_telemetry_strip,
    render_workspace_intro,
)

load_dotenv()
st.set_page_config(
    page_title="ArchTrace — Institutional Memory for Open Source",
    page_icon="⌘",
    layout="wide",
    initial_sidebar_state="collapsed",
)
init_db()


def build_adr_markdown(item: dict) -> str:
    """Generates a standard Architectural Decision Record (ADR) Markdown file."""
    lines = [
        f"# ADR-{item['id']:04d}: {item['title']}",
        "",
        f"- **Status:** {item['status']}",
        f"- **Source Thread:** {item['source_url']}",
        f"- **Affected Files:** {', '.join(item.get('affected_files', [])) or 'None tagged'}",
        f"- **Affected Symbols:** {', '.join(item.get('affected_symbols', [])) or 'None tagged'}",
        "",
        "## Decision",
        item.get("final_decision", ""),
        "",
        "## Rationale",
        item.get("rationale", ""),
        "",
        "## Rejected Alternatives",
    ]
    for alt in item.get("rejected_alternatives", []):
        lines.append(f"### Rejected: {alt.get('idea', 'Alternative')}")
        lines.append(f"- **Why Rejected:** {alt.get('reason_rejected', '')}")
        lines.append(f"- **Author:** {alt.get('author', 'unknown')}")
        lines.append(f"- **Source:** {alt.get('source_url', item['source_url'])}")
        lines.append(f"> \"{alt.get('verbatim_quote', '')}\"")
        lines.append("")
    return "\n".join(lines)


inject_console_css()

# Collapsed Sidebar for Engine & Model Settings
with st.sidebar:
    st.markdown("#### Engine Configuration")
    provider = st.selectbox(
        "LLM Provider",
        [
            "Groq (Free Open-Weight - Llama 3.1 8B)",
            "OpenRouter (Free Open-Weight)",
            "Offline Heuristic Mode (No API Key)",
        ],
    )
    default_key = os.getenv("LLM_API_KEY", "")
    api_key = ""
    if "Offline" not in provider:
        api_key = st.text_input("API Key", value=default_key, type="password")
        st.caption("Auto-discovers active open-weight models; falls back offline if blank.")

    with st.expander("Architecture Notes"):
        st.markdown(
            "- **Blind Evaluation:** Recovers rejected ideas with PEP text withheld\n"
            "- **Incremental Sync:** SHA-256 hashing skips unchanged comments\n"
            "- **Rename Tracking:** `git log --diff-filter=R` + Python `ast` symbols\n"
            "- **Episodic Memory:** Learns from `/archtrace helpful|obsolete`"
        )

    st.divider()
    if st.button("Reset Local Database", use_container_width=True):
        if os.path.exists(DEFAULT_DB_PATH):
            os.remove(DEFAULT_DB_PATH)
        init_db()
        st.session_state.pop("pr_matches", None)
        st.session_state.pop("pep_result", None)
        st.success("Database cleared.")

render_app_header()

# Primary Visual Interaction: Prominent Natural-Language Search
col_q1, col_q2 = st.columns([4.6, 1])
with col_q1:
    search_query = st.text_input(
        "Search architectural decisions",
        key="search_box",
        placeholder="Ask why a design was chosen or rejected, or filter by file path / symbol...",
        label_visibility="collapsed",
    )
with col_q2:
    show_obsolete = st.toggle("Include obsolete", value=False)

tab_guide, tab_repo, tab_pr, tab_bench = st.tabs([
    "Decision Explorer",
    "Index Repository",
    "PR Guardian",
    "Blind Benchmark",
])

# =====================================================================
# TAB 1: DECISION EXPLORER (NATURAL-LANGUAGE SEARCH & INVESTIGATION)
# =====================================================================
with tab_guide:

    # Secondary Quick-Filter Chips
    f1, f2, f3, f4 = st.columns(4)
    if f1.button("Filter: __note__", use_container_width=True):
        st.session_state["search_box"] = "__note__"
    if f2.button("Filter: subinterpreter", use_container_width=True):
        st.session_state["search_box"] = "subinterpreter"
    if f3.button("Filter: wsgi.py", use_container_width=True):
        st.session_state["search_box"] = "wsgi.py"
    if f4.button("Clear filter", use_container_width=True):
        st.session_state["search_box"] = ""

    stats = get_decision_stats()
    render_telemetry_strip(stats)

    if stats.get("top_files"):
        with st.expander("File Decision Hotspots"):
            st.bar_chart({fname: count for fname, count in stats["top_files"]})

    hits = search_decisions(search_query, include_obsolete=show_obsolete)

    if not hits:
        st.info(
            "No decisions matched your query. Clear the active filter above or index a repository in **Index Repository**."
        )
    else:
        bar_l, bar_r = st.columns([4, 1.2])
        with bar_l:
            st.caption(f"Showing {len(hits)} architectural decision record(s)")
        with bar_r:
            md_lines = ["# Architectural Decisions & Rejected Alternatives\n"]
            for d in hits:
                md_lines.append(
                    f"## {d['title']} (`{d['status']}`)\n"
                    f"- **Accepted Approach:** {d['final_decision']}\n"
                    f"- **Rationale:** {d['rationale']}\n"
                    f"- **Source:** {d['source_url']}\n"
                )
                for a in d.get("rejected_alternatives", []):
                    md_lines.append(f"  - **Rejected:** {a.get('idea')} — *{a.get('reason_rejected')}*\n")
            st.download_button(
                "Export All (.md)",
                data="\n".join(md_lines),
                file_name="ARCHTRACE_DECISIONS.md",
                mime="text/markdown",
                use_container_width=True,
            )

        for item in hits:
            render_decision_record(item, build_adr_markdown)

# =====================================================================
# TAB 2: INDEX ANY REPOSITORY OR FORUM
# =====================================================================
with tab_repo:
    st.markdown('<h2 class="sec-h2">Index Any Public Repository or Forum</h2>', unsafe_allow_html=True)
    st.markdown(
        '<p class="sec-sub">Extract unwritten architectural decisions from any GitHub repository, Issue/PR, Discourse thread, or Mailing List.</p>',
        unsafe_allow_html=True,
    )

    source_type = st.radio(
        "Source Type",
        [
            "GitHub Repository (Batch Scan)",
            "Single GitHub Issue / PR",
            "Discourse Forum Thread",
            "Public Mailing List Archive",
        ],
        horizontal=True,
    )

    if "Batch Scan" in source_type:
        c1, c2 = st.columns([3, 1])
        with c1:
            repo_slug = st.text_input("Public GitHub Repository (`owner/repo`)", value="pallets/flask")
        with c2:
            max_threads = st.number_input("Threads to scan", min_value=2, max_value=12, value=5)

        if st.button("Scan & Index Repository", type="primary"):
            with st.spinner(f"Reading top discussed issues & PRs in {repo_slug}..."):
                try:
                    threads = fetch_github_repo_threads(repo_slug, max_threads=int(max_threads))
                    from concurrent.futures import ThreadPoolExecutor

                    total_new, total_skipped = 0, 0
                    to_extract = []
                    for t in threads:
                        new_p, skip_p = filter_new_or_updated_posts(t["url"], t["posts"])
                        total_new += len(new_p)
                        total_skipped += skip_p
                        if new_p:
                            to_extract.append(t)

                    def _extract_thread(t):
                        return (t, extract_decisions_from_posts(t["url"], t["posts"], provider=provider, api_key=api_key))

                    with ThreadPoolExecutor(max_workers=4) as pool:
                        extracted_list = list(pool.map(_extract_thread, to_extract))

                    st.success(
                        f"Indexed **{len(extracted_list)} discussions** from `{repo_slug}`! "
                        f"({total_new} new posts analyzed, {total_skipped} unchanged skipped)"
                    )
                    for t, dec in extracted_list:
                        with st.expander(f"#{t['number']} — {dec.get('title', t['title'])}"):
                            st.write(f"**Decision:** {dec.get('final_decision')}")
                            st.caption(f"Engine: `{dec.get('extraction_mode', 'Heuristic')}`")
                except Exception as exc:
                    st.error(f"Could not index repository: {exc}")
    else:
        if "GitHub" in source_type:
            default_url = "https://github.com/pallets/flask/issues/4612"
        elif "Mailing List" in source_type:
            default_url = "https://mail.python.org/pipermail/python-dev/2021-October/165493.html"
        else:
            default_url = "https://discuss.python.org/t/pep-678-enriching-exceptions-with-notes/12641"

        url_input = st.text_input("Discussion URL", value=default_url)
        if st.button("Extract Decision", type="primary"):
            with st.spinner("Analyzing discussion..."):
                try:
                    if "GitHub" in source_type:
                        posts = fetch_github_discussion(url_input)
                    elif "Mailing List" in source_type:
                        posts = fetch_mailing_list_archive(url_input)
                    else:
                        posts = fetch_discourse_thread(url_input)
                    new_posts, skipped = filter_new_or_updated_posts(url_input, posts)
                    out = extract_decisions_from_posts(url_input, posts, provider=provider, api_key=api_key)
                    st.success(f"Saved! ({len(new_posts)} new, {skipped} skipped)")
                    st.write(f"**Decision:** {out.get('final_decision')}")
                except Exception as exc:
                    st.error(f"Failed: {exc}")

# =====================================================================
# TAB 3: PR GUARDIAN & CONTRIBUTOR PROFILES + RAW PR COMMENT PREVIEW
# =====================================================================
with tab_pr:
    st.markdown('<h2 class="sec-h2">Automated Pull Request Guardian & Rename Lineage</h2>', unsafe_allow_html=True)
    st.markdown(
        '<p class="sec-sub">Simulate how ArchTrace warns contributors on PRs even after files move or get renamed.</p>',
        unsafe_allow_html=True,
    )

    col_a, col_b = st.columns([1, 1.3], gap="large")
    with col_a:
        with st.container(border=True):
            st.markdown('<h3 class="card-h3">1. File Rename Lineage</h3>', unsafe_allow_html=True)
            st.write("")
            if st.button("🔄 Auto-Detect Git Renames", use_container_width=True):
                detected = sync_git_renames(".")
                st.success(f"Synced {detected} rename(s) from Git history.")
            old_p = st.text_input("Original File Path", value="Objects/exceptions.c")
            new_p = st.text_input("Renamed File Path", value="src/core/exception_types.c")
            if st.button("🔗 Link Renamed File", use_container_width=True):
                register_file_rename(old_p, new_p)
                st.success(f"Linked `{old_p}` ➡️ `{new_p}`")

    with col_b:
        with st.container(border=True):
            st.markdown('<h3 class="card-h3">2. Preview PR Memory Check</h3>', unsafe_allow_html=True)
            st.write("")
            pr_file = st.text_input("Modified File in PR", value="src/core/exception_types.c")
            pr_diff = st.text_area(
                "Proposed Code Change (Diff)",
                value="+ def attach_note(err):\n+     err.__note__ = 'retry failed'\n",
                height=115,
            )
            if st.button("Check Pull Request", type="primary", use_container_width=True):
                st.session_state["pr_matches"] = query_decisions_for_pr(pr_file, pr_diff)
                st.session_state["last_pr_file"] = pr_file
                if not st.session_state["pr_matches"]:
                    st.info("No conflicting decisions found for this diff.")

    pr_matches = st.session_state.get("pr_matches", [])
    if pr_matches:
        # Upgrade 4: Exact Raw GitHub PR Bot Comment Preview
        checked_file = st.session_state.get("last_pr_file", pr_file)
        raw_pr_comment = format_pr_comment([(checked_file, m) for m in pr_matches])
        with st.expander("👀 Preview Raw GitHub PR Bot Comment (Exact Markdown Posted by GitHub Action)"):
            st.code(raw_pr_comment, language="markdown")

        for m in pr_matches:
            with st.container(border=True):
                st.warning(f"**🏛️ PR Bot Alert:** {m['title']} (Confirmed helpful `{m['helpful_votes']}` times)")
                st.caption(f"Matched via: {', '.join(m['matched_reasons'])}")
                st.write(f"**Current Standard:** {m['final_decision']}")
                for alt in m["rejected_alternatives"]:
                    st.markdown(f"- **Rejected:** {alt.get('idea')} — *{alt.get('reason_rejected')}*")

                b1, b2, _ = st.columns([1, 1, 2])
                if b1.button(f"👍 Helpful (#{m['id']})", key=f"help_{m['id']}"):
                    record_pr_feedback(m["id"], "PR-DEMO", "HELPFUL", "Confirmed valid.")
                    st.success("Reinforced in episodic memory!")
                if b2.button(f"🗑️ Mark Outdated (#{m['id']})", key=f"obs_{m['id']}"):
                    record_pr_feedback(m["id"], "PR-DEMO", "OBSOLETE", "Superseded.")
                    st.info("Marked outdated—won't alert future PRs.")

    with st.expander("🪪 Cross-Platform Contributor Identity Resolution"):
        c1, c2, c3, c4 = st.columns(4)
        plat = c1.selectbox("Platform", ["github", "discourse", "mailing_list"])
        handle = c2.text_input("Handle", value="Zac-HD")
        d_name = c3.text_input("Display Name", value="Zac Hatfield-Dodds")
        email = c4.text_input("Email", value="")
        if st.button("Resolve Contributor"):
            cid = IdentityResolver.resolve(plat, handle, d_name, email)
            st.success(f"Unified Canonical ID: `{cid}`")
        conn = get_connection(DEFAULT_DB_PATH)
        rows = conn.execute("SELECT * FROM contributors").fetchall()
        conn.close()
        if rows:
            st.dataframe([dict(r) for r in rows], use_container_width=True)

# =====================================================================
# TAB 4: BLIND ACCURACY BENCHMARK (FOR JUDGES)
# =====================================================================
with tab_bench:
    st.markdown('<h2 class="sec-h2">Blind Decision Recovery Benchmark</h2>', unsafe_allow_html=True)
    st.markdown(
        '<p class="sec-sub">Evaluates ArchTrace on forum discussions alone while withholding the official PEP document.</p>',
        unsafe_allow_html=True,
    )

    selected_pep = st.selectbox("Select Benchmark Dataset", list(SAMPLE_PEP_BENCHMARKS.keys()))
    benchmark = SAMPLE_PEP_BENCHMARKS[selected_pep]

    c_run, c_live = st.columns([1, 2])
    fetch_live = c_live.checkbox("Fetch live thread from discuss.python.org (uncheck to use cached real posts)", value=True)
    if c_run.button("Run Blind Benchmark", type="primary"):
        with st.spinner("Extracting decisions (PEP hidden)..."):
            try:
                posts = fetch_discourse_thread(benchmark["discourse_url"], max_posts=25) if fetch_live else benchmark["cached_real_posts"]
            except Exception:
                posts = benchmark["cached_real_posts"]

            new_posts, skipped = filter_new_or_updated_posts(benchmark["discourse_url"], posts)
            extracted = extract_decisions_from_posts(benchmark["discourse_url"], posts, provider=provider, api_key=api_key)
            st.session_state["pep_result"] = extracted
            st.session_state["pep_benchmark"] = benchmark
            st.session_state["pep_sync"] = (len(new_posts), skipped)

    if "pep_result" in st.session_state:
        res = st.session_state["pep_result"]
        bench = st.session_state["pep_benchmark"]
        recall = compute_blind_recall(res.get("rejected_alternatives", []), bench["expected_keywords"])

        m1, m2, m3 = st.columns(3)
        m1.metric("Blind Recall Score", f"{recall['recall_percent']}%")
        m2.metric("Ground-Truth Ideas Recovered", f"{recall['matched_count']} / {recall['total_ground_truth']}")
        m3.metric("Extraction Engine", res.get("extraction_mode", "Heuristic").split("(")[0].strip())

        col_l, col_r = st.columns([1.2, 1], gap="large")
        with col_l:
            with st.container(border=True):
                st.markdown(f'<h3 class="card-h3">Extracted: {res.get("title")}</h3>', unsafe_allow_html=True)
                st.caption(f"Engine: `{res.get('extraction_mode', 'Heuristic')}`")
                st.write(f"**Chosen:** {res.get('final_decision')}")
                for alt in res.get("rejected_alternatives", []):
                    st.markdown(f"- **Rejected:** {alt.get('idea')} — *{alt.get('reason_rejected')}*")
        with col_r:
            with st.container(border=True):
                st.markdown(f'<h3 class="card-h3">🔑 Official {bench["pep_number"]} Answer Key</h3>', unsafe_allow_html=True)
                st.caption("Withheld during extraction")
                for item in bench["ground_truth_rejected_ideas"]:
                    st.markdown(f"- {item}")