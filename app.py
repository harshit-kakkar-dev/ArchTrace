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
    query_decisions_by_idea,
    query_decisions_for_pr,
    record_pr_feedback,
    register_file_rename,
    sync_git_renames,
)
from archtrace.identity import IdentityResolver
from archtrace.ingestion import (
    fetch_discourse_thread,
    fetch_github_discussion,
    fetch_github_repo_issues,
    filter_new_or_updated_posts,
)

load_dotenv()
st.set_page_config(page_title="ArchTrace — Architectural Decision Recovery", layout="wide")
init_db()

# Fix Streamlit's default red focus border on text boxes so it doesn't look like an error
st.markdown(
    """
    <style>
    div[data-baseweb="textarea"]:focus-within,
    div[data-baseweb="input"]:focus-within {
        border-color: #38bdf8 !important;
        box-shadow: 0 0 0 1px #38bdf8 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def render_decision_cards(matches: list, key_prefix: str) -> None:
    """Renders decision alerts directly under whichever search triggered them."""
    for m in matches:
        st.markdown("---")
        st.markdown(f"### 🤖 ArchTrace Historical Alert — Decision #{m['id']}")
        st.info(
            f"**🏛️ Institutional Memory Match**\n\n"
            f"- **Source Thread / Repo:** [{m['source_url']}]({m['source_url']})\n"
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
            if st.button(f"👍 /archtrace helpful (#{m['id']})", key=f"{key_prefix}_help_{m['id']}"):
                record_pr_feedback(m["id"], "PR-DEMO", "HELPFUL", "Maintainer confirmed warning is valid.")
                st.success("Episodic memory updated: decision reinforced!")
        with fb_col2:
            if st.button(f"🗑️ /archtrace obsolete (#{m['id']})", key=f"{key_prefix}_obs_{m['id']}"):
                record_pr_feedback(m["id"], "PR-DEMO", "OBSOLETE", "Decision superseded by newer architecture.")
                st.warning("Episodic memory updated: decision marked OBSOLETE and suppressed on future PRs!")


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
        "- **Whole-Repo Scan:** Paste any GitHub repo URL (no issue # needed)\n"
        "- **Ask Before You Code:** Plain-English idea check for new devs\n"
        "- **Git Rename Resilience:** `git log --diff-filter=R` + AST symbol matching\n"
        "- **Self-Improving Memory:** PR feedback updates active vs. obsolete decisions"
    )

    st.divider()
    if st.button("🗑️ Reset Local Database"):
        if os.path.exists(DEFAULT_DB_PATH):
            os.remove(DEFAULT_DB_PATH)
        init_db()
        st.session_state.pop("idea_matches", None)
        st.session_state.pop("pr_matches", None)
        st.session_state.pop("pep_result", None)
        st.success("Database cleared! Ready for a clean demo.")

tab1, tab2, tab3, tab4 = st.tabs([
    "🧪 1. Blind PEP Benchmark",
    "🌐 2. Multi-Source & Whole-Repo Ingestion",
    "🤖 3. Ask Before You Code & PR Bot",
    "🪪 4. Cross-Platform Identity",
])

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
# TAB 2: LIVE MULTI-SOURCE & WHOLE-REPO INGESTION
# =====================================================================
with tab2:
    st.subheader("Ingest an Entire GitHub Repo, a Single Issue/PR, or a Discourse Thread")
    source_type = st.radio(
        "Source Platform",
        ["Whole GitHub Repo (No Issue # Needed)", "Single GitHub Issue / PR", "Discourse Forum"],
        horizontal=True,
    )

    if source_type == "Whole GitHub Repo (No Issue # Needed)":
        repo_url = st.text_input(
            "Paste Public GitHub Repo URL",
            value="https://github.com/OSS-Initiatives-IIIT-Sonepat/vlabs-iiit-sonepat",
        )
        max_issues = st.slider("Top Discussed Issues/PRs to Scan", min_value=1, max_value=10, value=5)

        if st.button("🌐 Auto-Scan Whole Repository", type="primary"):
            with st.spinner("Scanning repository's most-discussed issues & PRs..."):
                try:
                    repo_threads = fetch_github_repo_issues(repo_url, max_issues=max_issues)
                    if not repo_threads:
                        st.warning("No public issues or PRs found in this repository.")
                    else:
                        total_new, total_skip = 0, 0
                        for issue_url, issue_title, posts in repo_threads:
                            new_p, skip_p = filter_new_or_updated_posts(issue_url, posts)
                            total_new += len(new_p)
                            total_skip += skip_p
                            extract_decisions_from_posts(
                                issue_url,
                                posts,
                                provider=provider,
                                api_key=api_key,
                            )
                        st.success(
                            f"Scanned **{len(repo_threads)}** top discussions from `{repo_url}`! "
                            f"({total_new} new posts analyzed, {total_skip} cached posts skipped.)"
                        )
                        st.info("Now switch to **Tab 3** and type any plain-English idea to check it against this repo's history!")
                except Exception as exc:
                    st.error(f"Repo scan failed: {exc}")

    else:
        default_url = (
            "https://github.com/pallets/flask/issues/3898"
            if "GitHub" in source_type
            else "https://discuss.python.org/t/pep-678-enriching-exceptions-with-notes/13374"
        )
        url_input = st.text_input("Public Thread URL", value=default_url)
        files_input = st.text_input("Optional File Path Tags (comma-separated)", value="Objects/exceptions.c, Lib/traceback.py")
        symbols_input = st.text_input("Optional Symbol Tags (comma-separated)", value="BaseException.add_note, __note__")

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
# TAB 3: PLAIN-ENGLISH IDEA CHECK + PR MEMORY BOT
# =====================================================================
with tab3:
    st.subheader("💡 Ask Before You Code (Plain-English Idea Check)")
    st.write(
        "New to the codebase? Describe the change you want to make in plain English—ArchTrace will check "
        "if your idea was already discussed or rejected in the past."
    )

    with st.form("idea_check_form"):
        idea_input = st.text_area(
            "What change do you want to make?",
            placeholder="Example: I want to redesign the function generator and microcontroller trainer components.",
            height=85,
        )
        submitted_idea = st.form_submit_button("🔎 Check My Idea Against Project History", type="primary")

    if submitted_idea:
        if not idea_input.strip():
            st.warning("Type your idea in plain English first!")
        else:
            idea_matches = query_decisions_by_idea(idea_input)
            st.session_state["idea_matches"] = idea_matches
            if not idea_matches:
                st.success("✅ No past conflicts or rejected decisions found for this idea!")

    # Render Plain-English results RIGHT HERE under the Plain-English box
    if st.session_state.get("idea_matches"):
        render_decision_cards(st.session_state["idea_matches"], key_prefix="idea")

    st.divider()
    st.subheader("🤖 Automated Pull Request Bot & Git Rename Lineage")

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

    if st.button("🔍 Run PR Decision Check"):
        matches = query_decisions_for_pr(pr_file, pr_diff)
        st.session_state["pr_matches"] = matches
        if not matches:
            st.warning("No matching active decisions found. Run Tab 1 or Tab 2 first to seed decisions!")

    # Render PR Bot results RIGHT HERE under the PR Bot section
    if st.session_state.get("pr_matches"):
        render_decision_cards(st.session_state["pr_matches"], key_prefix="pr")

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