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

load_dotenv()
st.set_page_config(
    page_title="ArchTrace — Institutional Memory for Open Source",
    page_icon="🧭",
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
        lines.append(f"### ❌ {alt.get('idea', 'Alternative')}")
        lines.append(f"- **Why Rejected:** {alt.get('reason_rejected', '')}")
        lines.append(f"- **Author:** {alt.get('author', 'unknown')}")
        lines.append(f"- **Source:** {alt.get('source_url', item['source_url'])}")
        lines.append(f"> \"{alt.get('verbatim_quote', '')}\"")
        lines.append("")
    return "\n".join(lines)


# Top Utility Bar with Live Light / Dark Theme Toggle
top_l, top_r = st.columns([4.5, 1])
with top_l:
    st.markdown(
        '<div style="padding-top:6px;font-size:0.85rem;font-weight:600;opacity:0.75;">'
        "🧭 Open-Source Contributor & Maintainer Portal"
        "</div>",
        unsafe_allow_html=True,
    )
with top_r:
    dark_mode = st.toggle("🌙 Dark Mode", value=True, key="ui_dark_mode")

active_theme = "dark" if dark_mode else "light"
components.html(
    f"""
    <script>
      window.parent.document.documentElement.setAttribute('data-theme', '{active_theme}');
    </script>
    """,
    height=0,
    width=0,
)

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap');

    :root, :root[data-theme="dark"] {
        --bg-canvas: #090D16;
        --bg-surface: #111827;
        --bg-input: #1E293B;
        --border-color: rgba(148, 163, 184, 0.2);
        --text-primary: #F8FAFC;
        --text-secondary: #94A3B8;
        --hero-bg: radial-gradient(circle at top right, rgba(6,182,212,0.25), transparent 50%),
                   linear-gradient(135deg, #1E1B4B 0%, #0F172A 100%);
        --hero-border: rgba(99, 102, 241, 0.4);
        --hero-title: #FFFFFF;
        --hero-tagline: #A5B4FC;
        --hero-body: #CBD5E1;
        --chosen-bg: rgba(16, 185, 129, 0.14);
        --chosen-text: #ECFDF5;
        --chip-bg: rgba(99, 102, 241, 0.18);
        --chip-text: #C7D2FE;
        --chip-border: rgba(129, 140, 248, 0.3);
        --shadow: 0 10px 28px rgba(0, 0, 0, 0.35);
    }

    :root[data-theme="light"] {
        --bg-canvas: #F4F7FB;
        --bg-surface: #FFFFFF;
        --bg-input: #F8FAFC;
        --border-color: #CBD5E1;
        --text-primary: #0F172A;
        --text-secondary: #475569;
        --hero-bg: radial-gradient(circle at top right, rgba(6,182,212,0.18), transparent 50%),
                   linear-gradient(135deg, #EEF2FF 0%, #E0F2FE 100%);
        --hero-border: #A5B4FC;
        --hero-title: #0F172A;
        --hero-tagline: #4338CA;
        --hero-body: #334155;
        --chosen-bg: #ECFDF5;
        --chosen-text: #064E3B;
        --chip-bg: #EEF2FF;
        --chip-text: #3730A3;
        --chip-border: #C7D2FE;
        --shadow: 0 8px 24px rgba(15, 23, 42, 0.07);
    }

    html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
        background-color: var(--bg-canvas) !important;
        color: var(--text-primary) !important;
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }

    .stMarkdown p, .stMarkdown li, .stMarkdown span, label, [data-testid="stWidgetLabel"] p,
    [data-testid="stCaptionContainer"], .stCaption {
        color: var(--text-primary) !important;
    }
    [data-testid="stCaptionContainer"] p {
        color: var(--text-secondary) !important;
    }

    [data-baseweb="input"] > div,
    [data-baseweb="textarea"] > div,
    [data-baseweb="select"] > div {
        background-color: var(--bg-input) !important;
        border-color: var(--border-color) !important;
        color: var(--text-primary) !important;
        border-radius: 10px !important;
    }
    input, textarea {
        color: var(--text-primary) !important;
        -webkit-text-fill-color: var(--text-primary) !important;
    }
    [data-testid="stExpander"] {
        background-color: var(--bg-surface) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 12px !important;
    }
    [data-testid="stExpander"] summary, [data-testid="stExpander"] summary p {
        color: var(--text-primary) !important;
    }

    .block-container {
        padding-top: 1.1rem !important;
        padding-bottom: 3rem !important;
        max-width: 1200px !important;
    }
    #MainMenu, footer, header[data-testid="stHeader"] {
        background: transparent !important;
    }

    .archtrace-hero {
        background: var(--hero-bg);
        border: 1px solid var(--hero-border);
        border-radius: 22px;
        padding: 2.2rem 2.5rem;
        margin: 0.35rem 0 1.5rem 0;
        box-shadow: var(--shadow);
    }
    .archtrace-hero h1 {
        color: var(--hero-title) !important;
        font-size: 2.65rem !important;
        font-weight: 800 !important;
        letter-spacing: -0.03em !important;
        line-height: 1.12 !important;
        margin: 0 0 0.35rem 0 !important;
    }
    .hero-tagline {
        color: var(--hero-tagline) !important;
        font-size: 1.25rem !important;
        font-weight: 700 !important;
        letter-spacing: -0.01em !important;
        margin: 0 0 0.7rem 0 !important;
    }
    .archtrace-hero p.hero-desc {
        color: var(--hero-body) !important;
        font-size: 1.02rem !important;
        line-height: 1.6 !important;
        margin: 0 !important;
        max-width: 820px;
    }

    h2.sec-h2 {
        color: var(--text-primary) !important;
        font-size: 1.45rem !important;
        font-weight: 700 !important;
        letter-spacing: -0.015em !important;
        margin: 0.4rem 0 0.2rem 0 !important;
    }
    p.sec-sub {
        color: var(--text-secondary) !important;
        font-size: 0.96rem !important;
        margin-bottom: 1.15rem !important;
    }
    h3.card-h3 {
        color: var(--text-primary) !important;
        font-size: 1.2rem !important;
        font-weight: 700 !important;
        margin: 0 !important;
    }
    h4.col-h4-good {
        color: #10B981 !important;
        font-size: 0.84rem !important;
        font-weight: 800 !important;
        letter-spacing: 0.06em !important;
        text-transform: uppercase !important;
        margin: 0 0 0.55rem 0 !important;
    }
    h4.col-h4-bad {
        color: #F43F5E !important;
        font-size: 0.84rem !important;
        font-weight: 800 !important;
        letter-spacing: 0.06em !important;
        text-transform: uppercase !important;
        margin: 0 0 0.55rem 0 !important;
    }

    div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: var(--bg-surface) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 16px !important;
        box-shadow: var(--shadow) !important;
        transition: transform 0.18s ease, border-color 0.18s ease;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        border-color: #6366F1 !important;
        transform: translateY(-2px);
    }

    .stTabs [data-baseweb="tab-list"] {
        background-color: var(--bg-surface) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 14px !important;
        padding: 0.35rem !important;
        gap: 0.4rem !important;
        box-shadow: var(--shadow);
    }
    .stTabs [data-baseweb="tab"] {
        color: var(--text-secondary) !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
        padding: 0.5rem 1.05rem !important;
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #4F46E5, #6366F1) !important;
        color: #FFFFFF !important;
    }

    .stButton > button, .stDownloadButton > button {
        background-color: var(--bg-surface) !important;
        color: var(--text-primary) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 10px !important;
        font-weight: 600 !important;
    }
    .stButton > button:hover, .stDownloadButton > button:hover {
        border-color: #6366F1 !important;
        color: #6366F1 !important;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #4F46E5, #6366F1) !important;
        color: #FFFFFF !important;
        border: none !important;
    }

    .chosen-box {
        background: var(--chosen-bg);
        border-left: 4px solid #10B981;
        color: var(--chosen-text);
        padding: 0.9rem 1.05rem;
        border-radius: 0 12px 12px 0;
        font-size: 0.96rem;
        line-height: 1.5;
        margin-bottom: 0.8rem;
    }
    .code-chip {
        display: inline-block;
        background: var(--chip-bg);
        color: var(--chip-text);
        border: 1px solid var(--chip-border);
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.76rem;
        padding: 0.18rem 0.55rem;
        border-radius: 7px;
        margin: 0.15rem 0.25rem 0.15rem 0;
    }
    .pill-active {
        background: rgba(16, 185, 129, 0.14);
        color: #10B981;
        border: 1px solid rgba(16, 185, 129, 0.35);
        padding: 0.22rem 0.72rem;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 700;
    }
    .pill-outdated {
        background: rgba(148, 163, 184, 0.16);
        color: var(--text-secondary);
        border: 1px solid var(--border-color);
        padding: 0.22rem 0.72rem;
        border-radius: 999px;
        font-size: 0.78rem;
        font-weight: 700;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Collapsed Sidebar for Maintainer & Model Controls
with st.sidebar:
    st.markdown("### ⚙️ Engine & Model Settings")
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
            "- **Blind Evaluation:** Recovers rejected ideas without seeing PEP text\n"
            "- **Incremental Sync:** SHA-256 hashing skips unchanged comments\n"
            "- **Rename Tracking:** `git log --diff-filter=R` + Python `ast` symbols\n"
            "- **Episodic Memory:** Learns from `/archtrace helpful|obsolete`"
        )

    st.divider()
    if st.button("🗑️ Reset Local Database", use_container_width=True):
        if os.path.exists(DEFAULT_DB_PATH):
            os.remove(DEFAULT_DB_PATH)
        init_db()
        st.session_state.pop("pr_matches", None)
        st.session_state.pop("pep_result", None)
        st.success("Database cleared!")

# Semantic H1 Hero Banner
st.markdown(
    """
    <div class="archtrace-hero">
        <h1>🧭 ArchTrace</h1>
        <div class="hero-tagline">Institutional Memory &amp; Unwritten Decision Recovery for Open Source</div>
        <p class="hero-desc">
            Understand why code was built this way before writing a single line. Ask in plain English, search any file path,
            or inspect rejected ideas to surface past architectural choices and original maintainer threads.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

tab_guide, tab_repo, tab_pr, tab_bench = st.tabs([
    "🧭 Contributor Explorer",
    "📥 Index Repository",
    "🤖 PR Guardian & Team",
    "🧪 Blind Benchmark",
])

# =====================================================================
# TAB 1: CONTRIBUTOR-FIRST DECISION EXPLORER + HOTSPOTS + ADR EXPORT
# =====================================================================
with tab_guide:
    # Upgrade 3: Decision Hotspots & Institutional Memory KPI Bar
    stats = get_decision_stats()
    if stats["total_decisions"] > 0:
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Decisions Tracked", stats["total_decisions"])
        k2.metric("Active Standards", stats["active_decisions"])
        k3.metric("Rejected Ideas Saved", stats["total_rejected_ideas"])
        top_file_label = stats["top_files"][0][0] if stats["top_files"] else "None tagged"
        k4.metric("Top Debated File", top_file_label)

        if stats["top_files"]:
            with st.expander("🔥 View Codebase Decision Hotspots (Most Debated Files)"):
                chart_data = {fname: count for fname, count in stats["top_files"]}
                st.bar_chart(chart_data)

    st.markdown('<h2 class="sec-h2">Explore Architectural Decisions</h2>', unsafe_allow_html=True)
    st.markdown(
        '<p class="sec-sub">Ask in plain English (e.g., <em>"I want to redesign the function generator"</em>) or search by file path / symbol.</p>',
        unsafe_allow_html=True,
    )

    p1, p2, p3, p4 = st.columns(4)
    if p1.button("✨ Exception `__notes__`", use_container_width=True):
        st.session_state["search_box"] = "__note__"
    if p2.button("✨ `list.discard()` vs `missing_ok`", use_container_width=True):
        st.session_state["search_box"] = "missing_ok"
    if p3.button("✨ Flask `wsgi.py` & Config", use_container_width=True):
        st.session_state["search_box"] = "wsgi.py"
    if p4.button("📚 Browse All Decisions", use_container_width=True):
        st.session_state["search_box"] = ""

    col_q1, col_q2 = st.columns([4.2, 1])
    with col_q1:
        search_query = st.text_input(
            "Search decisions",
            key="search_box",
            placeholder="🔎 Ask in plain English or enter a file/symbol (e.g., I want to change the microcontroller lab)...",
            label_visibility="collapsed",
        )
    with col_q2:
        show_obsolete = st.toggle("Show outdated", value=False)

    hits = search_decisions(search_query, include_obsolete=show_obsolete)
    all_active = search_decisions("", include_obsolete=False)
    total_rejected = sum(len(d["rejected_alternatives"]) for d in all_active)
    file_counts: dict[str, int] = {}
    for d in all_active:
        for f in d["affected_files"]:
            file_counts[f] = file_counts.get(f, 0) + 1
    top_file = max(file_counts.items(), key=lambda x: x[1])[0] if file_counts else "Objects/exceptions.c"

    m1, m2, m3 = st.columns(3)
    m1.metric("📚 Active Decisions Indexed", len(all_active))
    m2.metric("🚫 Rejected Ideas Captured", total_rejected)
    m3.metric("🔥 Top Debated File", top_file)
    if not hits:
        st.info(
            "👋 No decisions matched your query yet. Click **Browse All Decisions** above, "
            "or index a public repository in the **📥 Index Repository** tab."
        )
    else:
        md_lines = ["# Architectural Decisions & Rejected Alternatives\n"]
        for d in hits:
            md_lines.append(f"## {d['title']} (`{d['status']}`)\n- **Decision:** {d['final_decision']}\n- **Rationale:** {d['rationale']}\n- **Source:** {d['source_url']}\n")
            for a in d["rejected_alternatives"]:
                md_lines.append(f"  - ❌ **Rejected:** {a.get('idea')} — *{a.get('reason_rejected')}*\n")
        st.download_button(
            "📄 Export Decisions as ADR Markdown",
            data="\n".join(md_lines),
            file_name="ARCHTRACE_DECISIONS.md",
            mime="text/markdown",
        )
        st.caption(f"Showing **{len(hits)}** verified architectural decision brief(s)")
        for item in hits:
            with st.container(border=True):
                head_l, head_r = st.columns([4.5, 1])
                with head_l:
                    st.markdown(f'<h3 class="card-h3">📌 {item["title"]}</h3>', unsafe_allow_html=True)
                    if item.get("matched_keywords"):
                        kw_str = ", ".join(f"`{k}`" for k in item["matched_keywords"])
                        st.caption(f"Matched keywords: {kw_str}")
                with head_r:
                    badge_cls = "pill-active" if item["status"] == "ACTIVE" else "pill-outdated"
                    badge_txt = "● Active Standard" if item["status"] == "ACTIVE" else "○ Outdated"
                    st.markdown(f'<div style="text-align:right;"><span class="{badge_cls}">{badge_txt}</span></div>', unsafe_allow_html=True)

                st.write("")
                c_left, c_right = st.columns([1, 1.15], gap="large")

                with c_left:
                    st.markdown('<h4 class="col-h4-good">✅ What Was Chosen</h4>', unsafe_allow_html=True)
                    st.markdown(f'<div class="chosen-box">{item["final_decision"]}</div>', unsafe_allow_html=True)
                    st.markdown(f"**Rationale:** {item['rationale']}")

                    if item["affected_files"]:
                        chips = "".join(f'<span class="code-chip">📄 {f}</span>' for f in item["affected_files"])
                        st.markdown(f"**Files:** {chips}", unsafe_allow_html=True)
                    if item["affected_symbols"]:
                        sym_chips = "".join(f'<span class="code-chip">ƒ {s}</span>' for s in item["affected_symbols"][:6])
                        st.markdown(f"**Symbols:** {sym_chips}", unsafe_allow_html=True)

                    st.write("")
                    st.link_button("🔗 Read Original Discussion Thread", item["source_url"])
                    adr_lines = [
                        f"# ADR-{item['id']:03d}: {item['title']}",
                        f"- **Status:** {item['status']}",
                        f"- **Source Thread:** {item['source_url']}",
                        "",
                        "## Chosen Decision",
                        item["final_decision"],
                        "",
                        "## Rationale",
                        item["rationale"],
                        "",
                        "## Rejected Alternatives",
                    ]
                    for alt in item["rejected_alternatives"]:
                        adr_lines.append(f"- **{alt.get('idea')}**: {alt.get('reason_rejected')} *(Source: {alt.get('author')})*")

                    btn_c1, btn_c2 = st.columns(2)
                    with btn_c1:
                        st.link_button("🔗 Original Thread", item["source_url"], use_container_width=True)
                    with btn_c2:
                        st.download_button(
                            "📄 Export ADR (.md)",
                            data="\n".join(adr_lines),
                            file_name=f"ADR-{item['id']:03d}.md",
                            mime="text/markdown",
                            key=f"adr_dl_{item['id']}",
                            use_container_width=True,
                        )

                with c_right:
                    st.markdown('<h4 class="col-h4-bad">🚫 Rejected Alternatives (Do Not Re-Propose)</h4>', unsafe_allow_html=True)
                    for alt in item["rejected_alternatives"]:
                        with st.expander(f"❌ {alt.get('idea')}", expanded=True):
                            st.write(alt.get("reason_rejected"))
                            st.caption(f"Discussed by `{alt.get('author')}`")
                            st.markdown(f"> *\"{alt.get('verbatim_quote')}\"*")

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

        if st.button("🚀 Scan & Index Repository", type="primary"):
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
        if st.button("📥 Extract Decision", type="primary"):
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
            if st.button("🔍 Check Pull Request", type="primary", use_container_width=True):
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
                    st.markdown(f"- ❌ **{alt.get('idea')}** — *{alt.get('reason_rejected')}*")

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
    if c_run.button("🚀 Run Blind Benchmark", type="primary"):
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
                    st.markdown(f"- ❌ **{alt.get('idea')}** — *{alt.get('reason_rejected')}*")
        with col_r:
            with st.container(border=True):
                st.markdown(f'<h3 class="card-h3">🔑 Official {bench["pep_number"]} Answer Key</h3>', unsafe_allow_html=True)
                st.caption("Withheld during extraction")
                for item in bench["ground_truth_rejected_ideas"]:
                    st.markdown(f"- ✅ {item}")