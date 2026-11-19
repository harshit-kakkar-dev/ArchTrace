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


# Minimal Top Navigation Bar# Minimal Top Navigation Bar
top_l, top_r = st.columns([5, 1])
with top_l:
    st.markdown(
        '<div class="topbar-meta"><span class="brand-badge">ARCHTRACE</span>'
        '<span class="brand-sub">Architectural Decision &amp; Rationale Registry</span></div>',
        unsafe_allow_html=True,
    )
with top_r:
    dark_mode = st.toggle("Dark mode", value=False, key="ui_dark_mode")

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
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

    :root, :root[data-theme="light"] {
        --bg-canvas: #F6F8FC;
        --bg-surface: #FFFFFF;
        --bg-subtle: #EFF4FF;
        --bg-input: #FFFFFF;
        --border-color: #E2E8F0;
        --border-strong: #93C5FD;
        --text-primary: #0F172A;
        --text-secondary: #475569;
        --text-muted: #64748B;
        --accent-primary: #2563EB;
        --accent-hover: #1D4ED8;
        --accent-soft: #EFF6FF;
        --accent-border: #BFDBFE;
        --header-bg: linear-gradient(120deg, #FFFFFF 0%, #EFF6FF 55%, #F0FDF4 100%);
        --chosen-bg: #ECFDF5;
        --chosen-border: #10B981;
        --chosen-text: #065F46;
        --chip-bg: #F1F5F9;
        --chip-text: #1E293B;
        --chip-border: #CBD5E1;
        --card-shadow: 0 2px 10px rgba(15, 23, 42, 0.04);
    }

    :root[data-theme="dark"] {
        --bg-canvas: #0F172A;
        --bg-surface: #1E293B;
        --bg-subtle: #263349;
        --bg-input: #1E293B;
        --border-color: #334155;
        --border-strong: #38BDF8;
        --text-primary: #F8FAFC;
        --text-secondary: #CBD5E1;
        --text-muted: #94A3B8;
        --accent-primary: #38BDF8;
        --accent-hover: #0EA5E9;
        --accent-soft: rgba(56, 189, 248, 0.14);
        --accent-border: rgba(56, 189, 248, 0.35);
        --header-bg: linear-gradient(120deg, #1E293B 0%, #172554 60%, #0F292E 100%);
        --chosen-bg: rgba(16, 185, 129, 0.14);
        --chosen-border: #10B981;
        --chosen-text: #A7F3D0;
        --chip-bg: #0F172A;
        --chip-text: #E2E8F0;
        --chip-border: #334155;
        --card-shadow: 0 4px 16px rgba(2, 6, 23, 0.35);
    }

    html, body, .stApp, [data-testid="stAppViewContainer"], [data-testid="stMain"] {
        background-color: var(--bg-canvas) !important;
        color: var(--text-primary) !important;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
        -webkit-font-smoothing: antialiased;
    }

    code, pre, .stCode, .code-chip {
        font-family: 'JetBrains Mono', monospace !important;
    }

    .stMarkdown p, .stMarkdown li, .stMarkdown span, label, [data-testid="stWidgetLabel"] p {
        color: var(--text-primary) !important;
    }
    [data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p, .stCaption {
        color: var(--text-secondary) !important;
        font-size: 0.84rem !important;
    }

    .block-container {
        padding-top: 1.15rem !important;
        padding-bottom: 3rem !important;
        max-width: 1140px !important;
    }
    #MainMenu, footer, header[data-testid="stHeader"] {
        background: transparent !important;
    }

    .topbar-meta {
        display: flex;
        align-items: center;
        gap: 0.65rem;
        padding-top: 0.3rem;
    }
    .brand-badge {
        background: var(--accent-primary);
        color: #FFFFFF;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.06em;
        padding: 0.2rem 0.55rem;
        border-radius: 5px;
    }
    .brand-sub {
        color: var(--text-secondary);
        font-size: 0.85rem;
        font-weight: 500;
    }

    /* Vibrant Studio Header Card */
    .console-header {
        background: var(--header-bg);
        border: 1px solid var(--border-color);
        border-left: 4px solid var(--accent-primary);
        border-radius: 12px;
        padding: 1.35rem 1.6rem;
        margin: 0.3rem 0 1.25rem 0;
        box-shadow: var(--card-shadow);
    }
    .console-header h1 {
        color: var(--text-primary) !important;
        font-size: 1.85rem !important;
        font-weight: 700 !important;
        letter-spacing: -0.025em !important;
        line-height: 1.2 !important;
        margin: 0 0 0.35rem 0 !important;
    }
    .console-header p {
        color: var(--text-secondary) !important;
        font-size: 0.95rem !important;
        line-height: 1.55 !important;
        margin: 0 !important;
        max-width: 780px;
    }

    h2.sec-h2 {
        color: var(--text-primary) !important;
        font-size: 1.2rem !important;
        font-weight: 700 !important;
        letter-spacing: -0.015em !important;
        margin: 0.35rem 0 0.15rem 0 !important;
    }
    p.sec-sub {
        color: var(--text-secondary) !important;
        font-size: 0.9rem !important;
        margin-bottom: 1rem !important;
    }
    h3.card-h3 {
        color: var(--text-primary) !important;
        font-size: 1.08rem !important;
        font-weight: 700 !important;
        letter-spacing: -0.01em !important;
        margin: 0 !important;
    }
    h4.col-h4-good {
        color: #059669 !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.76rem !important;
        font-weight: 700 !important;
        letter-spacing: 0.05em !important;
        text-transform: uppercase !important;
        margin: 0 0 0.5rem 0 !important;
    }
    h4.col-h4-bad {
        color: #E11D48 !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.76rem !important;
        font-weight: 700 !important;
        letter-spacing: 0.05em !important;
        text-transform: uppercase !important;
        margin: 0 0 0.5rem 0 !important;
    }

    /* Clean Crisp Cards */
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: var(--bg-surface) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 10px !important;
        box-shadow: var(--card-shadow) !important;
    }
    div[data-testid="stVerticalBlockBorderWrapper"]:hover {
        border-color: var(--border-strong) !important;
    }

    /* Vibrant Pill-Underline Tabs */
    .stTabs [data-baseweb="tab-list"] {
        background-color: var(--bg-surface) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 10px !important;
        padding: 0.3rem !important;
        gap: 0.35rem !important;
        box-shadow: var(--card-shadow);
        margin-bottom: 1.1rem !important;
    }
    .stTabs [data-baseweb="tab"] {
        background: transparent !important;
        color: var(--text-secondary) !important;
        border-radius: 7px !important;
        font-weight: 600 !important;
        font-size: 0.9rem !important;
        padding: 0.45rem 1rem !important;
        border: none !important;
    }
    .stTabs [data-baseweb="tab"]:hover {
        background: var(--bg-subtle) !important;
        color: var(--text-primary) !important;
    }
    .stTabs [aria-selected="true"] {
        background: var(--accent-primary) !important;
        color: #FFFFFF !important;
        font-weight: 600 !important;
    }
    .stTabs [data-baseweb="tab-highlight"] {
        display: none !important;
    }

    /* Inputs & Expanders */
    [data-baseweb="input"] > div,
    [data-baseweb="textarea"] > div,
    [data-baseweb="select"] > div {
        background-color: var(--bg-input) !important;
        border: 1px solid var(--border-color) !important;
        color: var(--text-primary) !important;
        border-radius: 8px !important;
    }
    [data-baseweb="input"] > div:focus-within,
    [data-baseweb="textarea"] > div:focus-within {
        border-color: var(--accent-primary) !important;
        box-shadow: 0 0 0 2px var(--accent-soft) !important;
    }
    input, textarea {
        color: var(--text-primary) !important;
        -webkit-text-fill-color: var(--text-primary) !important;
    }
    [data-testid="stExpander"] {
        background-color: var(--bg-surface) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 8px !important;
    }
    [data-testid="stExpander"] summary, [data-testid="stExpander"] summary p {
        color: var(--text-primary) !important;
        font-size: 0.88rem !important;
        font-weight: 600 !important;
    }

    /* Vibrant Cobalt Buttons */
    .stButton > button, .stDownloadButton > button {
        background-color: var(--bg-surface) !important;
        color: var(--text-primary) !important;
        border: 1px solid var(--border-color) !important;
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 0.86rem !important;
        padding: 0.45rem 0.9rem !important;
        box-shadow: none !important;
    }
    .stButton > button:hover, .stDownloadButton > button:hover {
        background-color: var(--accent-soft) !important;
        border-color: var(--accent-primary) !important;
        color: var(--accent-primary) !important;
    }
    .stButton > button[kind="primary"] {
        background: var(--accent-primary) !important;
        color: #FFFFFF !important;
        border: 1px solid var(--accent-primary) !important;
        font-weight: 600 !important;
    }
    .stButton > button[kind="primary"]:hover {
        background: var(--accent-hover) !important;
        color: #FFFFFF !important;
    }

    /* Decision Callouts & Metadata Chips */
    .chosen-box {
        background: var(--chosen-bg);
        border-left: 4px solid var(--chosen-border);
        color: var(--chosen-text);
        padding: 0.8rem 1rem;
        border-radius: 0 8px 8px 0;
        font-size: 0.92rem;
        line-height: 1.55;
        margin-bottom: 0.75rem;
    }
    .code-chip {
        display: inline-block;
        background: var(--accent-soft);
        color: var(--accent-primary);
        border: 1px solid var(--accent-border);
        font-size: 0.76rem;
        font-weight: 500;
        padding: 0.16rem 0.52rem;
        border-radius: 5px;
        margin: 0.12rem 0.25rem 0.12rem 0;
    }
    .pill-active {
        background: rgba(16, 185, 129, 0.14);
        color: #059669;
        border: 1px solid rgba(16, 185, 129, 0.35);
        font-family: 'JetBrains Mono', monospace;
        padding: 0.18rem 0.6rem;
        border-radius: 999px;
        font-size: 0.73rem;
        font-weight: 700;
    }
    .pill-outdated {
        background: var(--chip-bg);
        color: var(--text-secondary);
        border: 1px solid var(--border-color);
        font-family: 'JetBrains Mono', monospace;
        padding: 0.18rem 0.6rem;
        border-radius: 999px;
        font-size: 0.73rem;
        font-weight: 600;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

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

# Minimal Editorial Header
st.markdown(
    """
    <div class="console-header">
        <h1>ArchTrace</h1>
        <p>
            Search architectural decisions, rejected design alternatives, and historical rationale across open-source discussions before modifying code.
        </p>
    </div>
    """,
    unsafe_allow_html=True,
)

tab_guide, tab_repo, tab_pr, tab_bench = st.tabs([
    "Decision Explorer",
    "Index Repository",
    "PR Guardian",
    "Blind Benchmark",
])

# =====================================================================
# TAB 1: CONTRIBUTOR-FIRST DECISION EXPLORER + HOTSPOTS + ADR EXPORT
# =====================================================================
with tab_guide:
    stats = get_decision_stats()
    if stats["total_decisions"] > 0:
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Decisions Indexed", stats["total_decisions"])
        k2.metric("Active Standards", stats["active_decisions"])
        k3.metric("Rejected Alternatives", stats["total_rejected_ideas"])
        top_file_label = stats["top_files"][0][0] if stats["top_files"] else "None"
        k4.metric("Top Debated File", top_file_label)

        if stats["top_files"]:
            with st.expander("Codebase Decision Hotspots"):
                chart_data = {fname: count for fname, count in stats["top_files"]}
                st.bar_chart(chart_data)

    st.markdown('<h2 class="sec-h2">Query Architectural History</h2>', unsafe_allow_html=True)
    st.markdown(
        '<p class="sec-sub">Search by plain-English intent, file path, symbol name, or rejected concept.</p>',
        unsafe_allow_html=True,
    )

    p1, p2, p3, p4 = st.columns(4)
    if p1.button("Filter: note / exceptions", use_container_width=True):
        st.session_state["search_box"] = "__note__"
    if p2.button("Filter: subinterpreter", use_container_width=True):
        st.session_state["search_box"] = "subinterpreter"
    if p3.button("Filter: wsgi.py", use_container_width=True):
        st.session_state["search_box"] = "wsgi.py"
    if p4.button("Show All Decisions", use_container_width=True):
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
            "or index a public repository in the **Index Repository** tab."
        )
    else:
        md_lines = ["# Architectural Decisions & Rejected Alternatives\n"]
        for d in hits:
            md_lines.append(f"## {d['title']} (`{d['status']}`)\n- **Decision:** {d['final_decision']}\n- **Rationale:** {d['rationale']}\n- **Source:** {d['source_url']}\n")
            for a in d["rejected_alternatives"]:
                md_lines.append(f"  - **Rejected:** {a.get('idea')} — *{a.get('reason_rejected')}*\n")
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
                    st.markdown('<h4 class="col-h4-good">Accepted Decision</h4>', unsafe_allow_html=True)
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
                        with st.expander(f"Rejected: {alt.get('idea')}", expanded=True):
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