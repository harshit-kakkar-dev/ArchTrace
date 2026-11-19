import os
import sys
from pathlib import Path
import streamlit as st
from dotenv import load_dotenv

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
st.set_page_config(
    page_title="ArchTrace — Contributor Decision Guide",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="collapsed",
)
init_db()

# Subtle visual polish
st.markdown(
    """
    <style>
    .block-container { padding-top: 2rem; max-width: 1150px; }
    .hero-box {
        background: linear-gradient(135deg, rgba(99,102,241,0.12), rgba(16,185,129,0.08));
        border: 1px solid rgba(128,128,128,0.2);
        border-radius: 14px;
        padding: 1.4rem 1.8rem;
        margin-bottom: 1.2rem;
    }
    .hero-title { font-size: 1.85rem; font-weight: 700; margin-bottom: 0.25rem; }
    .hero-sub { font-size: 1.02rem; opacity: 0.85; margin-bottom: 0; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Collapsed Sidebar for Judges / Maintainers
with st.sidebar:
    st.header("⚙️ Engine & Model Settings")
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
        api_key = st.text_input("API Key (Groq / OpenRouter)", value=default_key, type="password")
        st.caption("Auto-discovers active open-weight models; falls back offline if blank.")

    with st.expander("📐 Under the Hood (For Judges)"):
        st.markdown(
            "- **Blind Evaluation:** Recovers rejected ideas without seeing PEP docs\n"
            "- **Incremental Sync:** SHA-256 hashing skips unchanged comments\n"
            "- **Rename Tracking:** `git log --diff-filter=R` + Python `ast` symbols\n"
            "- **Episodic Memory:** Learns from `/archtrace helpful|obsolete`"
        )

# Welcoming Hero Header
st.markdown(
    """
    <div class="hero-box">
        <div class="hero-title">🧭 ArchTrace — Understand Why Code Was Built This Way</div>
        <p class="hero-sub">
            New to the project? Search any feature, file, or idea before opening a Pull Request to see
            past architectural decisions, rejected approaches, and original maintainer discussions.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

tab_guide, tab_repo, tab_pr, tab_bench = st.tabs([
    "🧭 Contributor Decision Explorer",
    "📥 Index Any Repository",
    "🤖 PR Guardian & Contributors",
    "🧪 Accuracy Benchmark",
])

# =====================================================================
# TAB 1: CONTRIBUTOR-FIRST DECISION EXPLORER
# =====================================================================
with tab_guide:
    st.markdown("#### 💡 Try a quick search or type your own question below")
    p_col1, p_col2, p_col3, p_col4 = st.columns(4)
    if p_col1.button("🔍 Exception `__notes__`", use_container_width=True):
        st.session_state["search_box"] = "__note__"
    if p_col2.button("🔍 `list.discard()` vs `missing_ok`", use_container_width=True):
        st.session_state["search_box"] = "missing_ok"
    if p_col3.button("🔍 Flask `wsgi.py` / config", use_container_width=True):
        st.session_state["search_box"] = "wsgi.py"
    if p_col4.button("📚 Show All Decisions", use_container_width=True):
        st.session_state["search_box"] = ""

    col_q1, col_q2 = st.columns([4, 1])
    with col_q1:
        search_query = st.text_input(
            "Search by feature, file name, or function",
            key="search_box",
            placeholder="e.g., __note__, missing_ok, Objects/exceptions.c, wsgi.py...",
            label_visibility="collapsed",
        )
    with col_q2:
        show_obsolete = st.toggle("Show outdated", value=False)

    hits = search_decisions(search_query, include_obsolete=show_obsolete)

    if not hits:
        st.info(
            "👋 No decisions matched your search yet! Click **Show All Decisions** above, "
            "or index a repository in the **📥 Index Any Repository** tab."
        )
    else:
        st.caption(f"Found **{len(hits)}** architectural decision brief(s)")
        for item in hits:
            with st.container(border=True):
                top_l, top_r = st.columns([4, 1])
                with top_l:
                    st.markdown(f"### 📌 {item['title']}")
                with top_r:
                    badge = "🟢 Active Standard" if item["status"] == "ACTIVE" else "⚪ Outdated"
                    st.markdown(f"**{badge}**")

                c_left, c_right = st.columns([1, 1.15], gap="large")
                with c_left:
                    st.markdown("#### ✅ What Was Chosen")
                    st.success(item["final_decision"])
                    st.markdown(f"**Why it won:** {item['rationale']}")

                    files_str = ", ".join(f"`{f}`" for f in item["affected_files"]) or "_None tagged_"
                    syms_str = ", ".join(f"`{s}`" for s in item["affected_symbols"][:6]) or "_None tagged_"
                    st.markdown(f"**Related Files:** {files_str}")
                    st.markdown(f"**Key Symbols:** {syms_str}")
                    st.link_button("🔗 Read Original Discussion", item["source_url"])

                with c_right:
                    st.markdown("#### 🚫 Rejected Ideas (Avoid Re-Proposing)")
                    for alt in item["rejected_alternatives"]:
                        with st.expander(f"❌ {alt.get('idea')}", expanded=True):
                            st.write(alt.get("reason_rejected"))
                            st.caption(f"Proposed/discussed by `{alt.get('author')}`")
                            st.markdown(f"> *\"{alt.get('verbatim_quote')}\"*")

# =====================================================================
# TAB 2: INDEX ANY REPOSITORY OR FORUM
# =====================================================================
with tab_repo:
    st.subheader("📥 Build Institutional Memory for Any Project")
    st.write("Point ArchTrace at any public GitHub repository, Issue/PR, or Discourse thread to extract its hidden design history.")

    source_type = st.radio(
        "Source Type",
        ["GitHub Repository (Batch Scan)", "Single GitHub Issue / PR", "Discourse Forum Thread"],
        horizontal=True,
    )

    if "Batch Scan" in source_type:
        c1, c2 = st.columns([3, 1])
        with c1:
            repo_slug = st.text_input("Repository (`owner/repo`)", value="pallets/flask")
        with c2:
            max_threads = st.number_input("Threads to scan", min_value=2, max_value=12, value=5)

        if st.button("🚀 Scan & Index Repository", type="primary"):
            with st.spinner(f"Reading top discussed issues & PRs in {repo_slug}..."):
                try:
                    threads = fetch_github_repo_threads(repo_slug, max_threads=int(max_threads))
                    total_new, total_skipped = 0, 0
                    extracted_list = []
                    for t in threads:
                        new_p, skip_p = filter_new_or_updated_posts(t["url"], t["posts"])
                        total_new += len(new_p)
                        total_skipped += skip_p
                        if new_p or skip_p:
                            dec = extract_decisions_from_posts(t["url"], t["posts"], provider=provider, api_key=api_key)
                            extracted_list.append((t, dec))

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
        default_url = (
            "https://github.com/pallets/flask/issues/4612"
            if "GitHub" in source_type
            else "https://discuss.python.org/t/pep-678-enriching-exceptions-with-notes/12641"
        )
        url_input = st.text_input("Discussion URL", value=default_url)
        if st.button("📥 Extract Decision", type="primary"):
            with st.spinner("Analyzing discussion..."):
                try:
                    posts = fetch_github_discussion(url_input) if "GitHub" in source_type else fetch_discourse_thread(url_input)
                    new_posts, skipped = filter_new_or_updated_posts(url_input, posts)
                    out = extract_decisions_from_posts(url_input, posts, provider=provider, api_key=api_key)
                    st.success(f"Saved! ({len(new_posts)} new, {skipped} skipped)")
                    st.write(f"**Decision:** {out.get('final_decision')}")
                except Exception as exc:
                    st.error(f"Failed: {exc}")

# =====================================================================
# TAB 3: PR GUARDIAN & CONTRIBUTOR PROFILES
# =====================================================================
with tab_pr:
    st.subheader("🤖 Automated Pull Request Guard & Rename Tracking")
    st.write("Test how ArchTrace warns contributors on Pull Requests—even after files are moved or renamed.")

    col_a, col_b = st.columns([1, 1.3], gap="large")
    with col_a:
        with st.container(border=True):
            st.markdown("#### 1. File Move / Rename Lineage")
            if st.button("🔄 Auto-Detect Git Renames", use_container_width=True):
                detected = sync_git_renames(".")
                st.success(f"Synced {detected} rename(s) from Git history.")
            old_p = st.text_input("Old File Path", value="Objects/exceptions.c")
            new_p = st.text_input("New File Path", value="src/core/exception_types.c")
            if st.button("🔗 Link Renamed File", use_container_width=True):
                register_file_rename(old_p, new_p)
                st.success(f"Linked `{old_p}` ➡️ `{new_p}`")

    with col_b:
        with st.container(border=True):
            st.markdown("#### 2. Preview PR Check")
            pr_file = st.text_input("Modified File in PR", value="src/core/exception_types.c")
            pr_diff = st.text_area(
                "Proposed Code Change (Diff)",
                value="+ def attach_note(err):\n+     err.__note__ = 'retry failed'\n",
                height=115,
            )
            if st.button("🔍 Check Pull Request", type="primary", use_container_width=True):
                st.session_state["pr_matches"] = query_decisions_for_pr(pr_file, pr_diff)
                if not st.session_state["pr_matches"]:
                    st.info("No conflicting decisions found for this diff.")

    for m in st.session_state.get("pr_matches", []):
        with st.container(border=True):
            st.warning(f"**🏛️ PR Bot Alert:** {m['title']} (Confirmed helpful `{m['helpful_votes']}` times)")
            st.caption(f"Matched via: {', '.join(m['matched_reasons'])}")
            st.write(f"**Current Standard:** {m['final_decision']}")
            for alt in m["rejected_alternatives"]:
                st.markdown(f"- ❌ **{alt.get('idea')}** — *{alt.get('reason_rejected')}*")

            b1, b2, _ = st.columns([1, 1, 2])
            if b1.button(f"👍 Helpful (#{m['id']})", key=f"help_{m['id']}"):
                record_pr_feedback(m["id"], "PR-DEMO", "HELPFUL", "Confirmed valid.")
                st.success("Reinforced in memory!")
            if b2.button(f"🗑️ Mark Outdated (#{m['id']})", key=f"obs_{m['id']}"):
                record_pr_feedback(m["id"], "PR-DEMO", "OBSOLETE", "Superseded.")
                st.info("Marked outdated—won't alert future PRs.")

    with st.expander("🪪 Cross-Platform Contributor Identity Table"):
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
    st.subheader("🧪 Blind Decision Recovery Benchmark")
    st.write("Proves ArchTrace can recover a PEP's rejected alternatives from forum discussions alone—with the PEP withheld.")

    selected_pep = st.selectbox("Benchmark Dataset", list(SAMPLE_PEP_BENCHMARKS.keys()))
    benchmark = SAMPLE_PEP_BENCHMARKS[selected_pep]

    c_run, c_live = st.columns([1, 2])
    fetch_live = c_live.checkbox("Fetch live thread from discuss.python.org", value=False)
    if c_run.button("🚀 Run Blind Benchmark", type="primary"):
        with st.spinner("Extracting decisions (PEP hidden)..."):
            try:
                posts = fetch_discourse_thread(benchmark["discourse_url"], max_posts=25) if fetch_live else benchmark["synthetic_discussion_posts"]
            except Exception:
                posts = benchmark["synthetic_discussion_posts"]

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
                st.markdown(f"#### Extracted: {res.get('title')}")
                st.caption(f"Engine: `{res.get('extraction_mode', 'Heuristic')}`")
                st.write(f"**Chosen:** {res.get('final_decision')}")
                for alt in res.get("rejected_alternatives", []):
                    st.markdown(f"- ❌ **{alt.get('idea')}** — *{alt.get('reason_rejected')}*")
        with col_r:
            with st.container(border=True):
                st.markdown(f"#### 🔑 Official {bench['pep_number']} Answer Key")
                st.caption("Withheld during extraction")
                for item in bench["ground_truth_rejected_ideas"]:
                    st.markdown(f"- ✅ {item}")