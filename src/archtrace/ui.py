"""Reusable design tokens and engineering-console UI components for ArchTrace."""

from __future__ import annotations

import html
from typing import Callable, Dict, List
import streamlit as st

COLORS = {
    "bg_canvas": "#0D1117",
    "bg_surface": "#161B22",
    "bg_subtle": "#1C2128",
    "border_default": "#30363D",
    "border_muted": "#21262D",
    "text_primary": "#E6EDF3",
    "text_secondary": "#8B949E",
    "text_muted": "#6E7681",
    "accent_blue": "#2F81F7",
    "outcome_accepted": "#3FB950",
    "outcome_accepted_bg": "rgba(63, 185, 80, 0.07)",
    "outcome_rejected": "#F85149",
    "outcome_rejected_bg": "rgba(248, 81, 73, 0.07)",
    "status_active": "#58A6FF",
    "status_obsolete": "#8B949E",
}


def inject_console_css() -> None:
    """Applies restrained typography, thin hairline borders, and search-first hierarchy."""
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

        html, body, .stApp {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            -webkit-font-smoothing: antialiased;
        }}
        code, pre, .mono {{
            font-family: 'JetBrains Mono', monospace !important;
        }}
        .block-container {{
            padding-top: 1.25rem !important;
            padding-bottom: 3rem !important;
            max-width: 1120px !important;
        }}
        #MainMenu, footer, header[data-testid="stHeader"] {{
            background: transparent !important;
        }}

        /* Prominent Product Identity & Compact Workspace Header */
        .at-hero-header {{
            padding: 0.15rem 0 0.75rem 0;
        }}
        .at-brand-lockup {{
            display: flex;
            align-items: center;
            flex-wrap: wrap;
            gap: 0.9rem;
            margin-bottom: 0.65rem;
        }}
        .at-logo-svg {{
            width: 44px;
            height: 44px;
            flex-shrink: 0;
            display: block;
        }}
        .at-brand-text {{
            display: flex;
            flex-direction: column;
            justify-content: center;
        }}
        .at-product-name {{
            font-size: clamp(2rem, 4vw, 2.75rem);
            font-weight: 700;
            letter-spacing: -0.03em;
            line-height: 1.05;
            color: {COLORS["text_primary"]};
            margin: 0;
        }}
        .at-descriptor {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.72rem;
            font-weight: 600;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            color: {COLORS["status_active"]};
            margin-top: 0.25rem;
        }}
        .at-tagline {{
            font-size: clamp(1.05rem, 1.8vw, 1.2rem);
            font-weight: 500;
            letter-spacing: -0.015em;
            line-height: 1.35;
            color: {COLORS["text_primary"]};
            margin: 0 0 0.28rem 0;
        }}
        .at-supporting-copy {{
            font-size: 0.88rem;
            line-height: 1.5;
            color: {COLORS["text_secondary"]};
            margin: 0;
            max-width: 740px;
        }}

        @media (max-width: 640px) {{
            .at-logo-svg {{
                width: 36px;
                height: 36px;
            }}
            .at-brand-lockup {{
                gap: 0.65rem;
            }}
        }}

        /* Primary Natural-Language Search Input Emphasis */
        div[data-testid="stTextInput"] input {{
            font-size: 0.94rem !important;
            padding: 0.62rem 0.85rem !important;
            border-radius: 6px !important;
            border: 1px solid {COLORS["border_default"]} !important;
            background-color: {COLORS["bg_surface"]} !important;
        }}
        div[data-testid="stTextInput"] input:focus {{
            border-color: {COLORS["accent_blue"]} !important;
            box-shadow: 0 0 0 1px {COLORS["accent_blue"]} !important;
        }}

        /* Clean Underline Navigation Tabs */
        .stTabs [data-baseweb="tab-list"] {{
            border-top: 1px solid {COLORS["border_default"]} !important;
            border-bottom: 1px solid {COLORS["border_default"]} !important;
            gap: 1.5rem !important;
            margin-top: 0.35rem !important;
            margin-bottom: 1rem !important;
            padding-top: 0.15rem !important;
        }}
        .stTabs [data-baseweb="tab"] {{
            background: transparent !important;
            color: {COLORS["text_secondary"]} !important;
            font-size: 0.86rem !important;
            font-weight: 500 !important;
            padding: 0.45rem 0.1rem !important;
        }}
        .stTabs [aria-selected="true"] {{
            color: {COLORS["text_primary"]} !important;
            font-weight: 600 !important;
        }}
        .stTabs [data-baseweb="tab-highlight"] {{
            background-color: {COLORS["accent_blue"]} !important;
            height: 2px !important;
        }}

        /* Compact Telemetry Strip */
        .at-telemetry {{
            display: flex;
            flex-wrap: wrap;
            align-items: center;
            gap: 1.35rem;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.76rem;
            color: {COLORS["text_secondary"]};
            background: {COLORS["bg_surface"]};
            border: 1px solid {COLORS["border_muted"]};
            border-radius: 6px;
            padding: 0.45rem 0.8rem;
            margin: 0.55rem 0 0.85rem 0;
        }}
        .at-telemetry strong {{
            color: {COLORS["text_primary"]};
            font-weight: 600;
        }}

        /* Thin Hairline Decision Containers */
        div[data-testid="stVerticalBlockBorderWrapper"] {{
            background-color: {COLORS["bg_surface"]} !important;
            border: 1px solid {COLORS["border_default"]} !important;
            border-radius: 6px !important;
        }}

        /* Decision Record Header & Typographic Hierarchy */
        .at-rec-title {{
            font-size: 1.04rem;
            font-weight: 600;
            letter-spacing: -0.015em;
            line-height: 1.35;
            color: {COLORS["text_primary"]};
            margin: 0 0 0.25rem 0;
        }}
        .at-rec-divider {{
            border-bottom: 1px solid {COLORS["border_muted"]};
            margin: 0.55rem 0 0.75rem 0;
        }}

        /* Lifecycle Status Badges (ACTIVE vs OBSOLETE) */
        .badge-lifecycle-active {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.69rem;
            font-weight: 600;
            letter-spacing: 0.03em;
            color: {COLORS["status_active"]};
            border: 1px solid rgba(88, 166, 255, 0.35);
            background: rgba(47, 129, 247, 0.1);
            padding: 0.14rem 0.5rem;
            border-radius: 4px;
        }}
        .badge-lifecycle-obsolete {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.69rem;
            font-weight: 600;
            letter-spacing: 0.03em;
            color: {COLORS["status_obsolete"]};
            border: 1px solid {COLORS["border_default"]};
            background: {COLORS["bg_subtle"]};
            padding: 0.14rem 0.5rem;
            border-radius: 4px;
        }}

        /* Design Outcome Section Headers (ACCEPTED vs REJECTED) */
        .outcome-header {{
            display: flex;
            align-items: center;
            gap: 0.45rem;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.72rem;
            font-weight: 600;
            letter-spacing: 0.05em;
            text-transform: uppercase;
            margin-bottom: 0.5rem;
        }}
        .outcome-header-accepted {{
            color: {COLORS["outcome_accepted"]};
        }}
        .outcome-header-rejected {{
            color: {COLORS["outcome_rejected"]};
        }}
        .dot-accepted {{
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: {COLORS["outcome_accepted"]};
            display: inline-block;
        }}
        .dot-rejected {{
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: {COLORS["outcome_rejected"]};
            display: inline-block;
        }}
        .count-pill {{
            font-size: 0.68rem;
            color: {COLORS["text_secondary"]};
            background: {COLORS["bg_canvas"]};
            border: 1px solid {COLORS["border_default"]};
            border-radius: 999px;
            padding: 0.02rem 0.42rem;
        }}

        .accepted-callout {{
            background: {COLORS["outcome_accepted_bg"]};
            border-left: 2px solid {COLORS["outcome_accepted"]};
            padding: 0.65rem 0.85rem;
            border-radius: 0 4px 4px 0;
            font-size: 0.91rem;
            font-weight: 500;
            line-height: 1.5;
            color: {COLORS["text_primary"]};
            margin-bottom: 0.65rem;
        }}
        .rationale-copy {{
            font-size: 0.87rem;
            line-height: 1.55;
            color: {COLORS["text_secondary"]};
            margin-bottom: 0.75rem;
        }}
        .rationale-copy strong {{
            color: {COLORS["text_primary"]};
            font-weight: 600;
        }}

        .rejected-item {{
            background: {COLORS["bg_canvas"]};
            border: 1px solid {COLORS["border_muted"]};
            border-left: 2px solid {COLORS["outcome_rejected"]};
            border-radius: 4px;
            padding: 0.6rem 0.8rem;
            margin-bottom: 0.5rem;
        }}
        .rejected-idea-title {{
            font-size: 0.88rem;
            font-weight: 600;
            line-height: 1.35;
            color: {COLORS["text_primary"]};
            margin-bottom: 0.25rem;
        }}
        .rejected-reason {{
            font-size: 0.83rem;
            color: {COLORS["text_secondary"]};
            line-height: 1.45;
        }}
        .rejected-meta {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.73rem;
            color: {COLORS["text_muted"]};
            margin-top: 0.3rem;
        }}
        .rejected-quote {{
            font-size: 0.8rem;
            color: {COLORS["text_secondary"]};
            border-left: 2px solid {COLORS["border_default"]};
            padding-left: 0.6rem;
            margin-top: 0.4rem;
            line-height: 1.45;
            font-style: italic;
        }}

        .meta-row {{
            margin-top: 0.25rem;
        }}
        .meta-tag {{
            display: inline-block;
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.72rem;
            color: {COLORS["text_secondary"]};
            background: {COLORS["bg_canvas"]};
            border: 1px solid {COLORS["border_default"]};
            border-radius: 4px;
            padding: 0.1rem 0.45rem;
            margin: 0.12rem 0.25rem 0.12rem 0;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_app_header() -> None:
    """Renders the prominent ArchTrace identity with the faceted A-ribbon mark and workspace framing."""
    st.markdown(
        """
        <div class="at-hero-header">
            <div class="at-brand-lockup">
                <svg class="at-logo-svg" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg" aria-label="ArchTrace logo">
                    <!-- Faceted Left Ribbon Leg -->
                    <path d="M9 55L26.5 14.5C27.6 12 30 10.5 32.7 10.5L36.5 18.5L21.5 55H9Z" fill="#1D4ED8"/>
                    <path d="M14.2 43L26.5 14.5C27.5 12.2 29.6 10.8 32 10.5L36.5 18.5L26 43H14.2Z" fill="#2563EB"/>
                    <!-- Faceted Right Ribbon Leg -->
                    <path d="M27.2 13.5C28.4 11.3 30.8 10 33.4 10C36 10 38.4 11.4 39.6 13.7L55 55H42.2L27.2 13.5Z" fill="#38BDF8"/>
                    <path d="M27.2 13.5C28.4 11.3 30.8 10 33.4 10C35.4 10 37.3 10.8 38.6 12.2L44.8 28.5L33.5 31L27.2 13.5Z" fill="#60A5FA"/>
                    <!-- Inner Counter Arch -->
                    <path d="M26.2 44.5L30.2 35.8C31.1 33.9 33.8 33.9 34.7 35.9L39 55H29.4L26.2 44.5Z" fill="#2F81F7"/>
                </svg>
                <div class="at-brand-text">
                    <h1 class="at-product-name">ArchTrace</h1>
                    <div class="at-descriptor">ARCHITECTURAL MEMORY ENGINE</div>
                </div>
            </div>
            <div class="at-tagline">Understand why the code is this way.</div>
            <p class="at-supporting-copy">
                Query institutional memory and recovered design rationale across historical discussions—inspect accepted approaches, rejected alternatives, and affected code paths before changing implementation.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_workspace_intro() -> None:
    """Backward-compatible no-op; workspace framing is now unified inside render_app_header()."""
    return None


def render_telemetry_strip(stats: Dict) -> None:
    """Renders a single-line monospace telemetry bar without oversized metric cards."""
    if not stats or stats.get("total_decisions", 0) <= 0:
        return
    top_files = stats.get("top_files") or []
    hotspot = html.escape(top_files[0][0]) if top_files else "none"
    st.markdown(
        f"""
        <div class="at-telemetry">
            <span>indexed: <strong>{stats.get("total_decisions", 0)}</strong></span>
            <span>active: <strong>{stats.get("active_decisions", 0)}</strong></span>
            <span>rejected_alternatives: <strong>{stats.get("total_rejected_ideas", 0)}</strong></span>
            <span>top_hotspot: <strong>{hotspot}</strong></span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_decision_record(item: Dict, build_adr_fn: Callable[[Dict], str]) -> None:
    """Data-driven decision record separating lifecycle status (ACTIVE/OBSOLETE) from outcome (ACCEPTED/REJECTED)."""
    status = str(item.get("status") or "ACTIVE").upper()
    is_active = status == "ACTIVE"
    lifecycle_cls = "badge-lifecycle-active" if is_active else "badge-lifecycle-obsolete"
    lifecycle_label = "ACTIVE" if is_active else "OBSOLETE"

    title = html.escape(str(item.get("title") or "Untitled Decision"))
    final_decision = html.escape(str(item.get("final_decision") or "No final decision recorded."))
    rationale = html.escape(str(item.get("rationale") or "").strip())
    source_url = str(item.get("source_url") or "").strip()
    affected_files: List[str] = [str(f) for f in (item.get("affected_files") or []) if f]
    affected_symbols: List[str] = [str(s) for s in (item.get("affected_symbols") or []) if s]
    rejected_alts: List[Dict] = list(item.get("rejected_alternatives") or [])
    matched_kw: List[str] = [str(k) for k in (item.get("matched_keywords") or []) if k]

    with st.container(border=True):
        h_left, h_right = st.columns([5.2, 1])
        with h_left:
            st.markdown(f'<div class="at-rec-title">{title}</div>', unsafe_allow_html=True)
            meta_parts = []
            for k in matched_kw:
                meta_parts.append(f'<span class="meta-tag">match:{html.escape(k)}</span>')
            for f in affected_files:
                meta_parts.append(f'<span class="meta-tag">{html.escape(f)}</span>')
            for s in affected_symbols[:8]:
                meta_parts.append(f'<span class="meta-tag">{html.escape(s)}()</span>')
            if meta_parts:
                st.markdown(f'<div class="meta-row">{"".join(meta_parts)}</div>', unsafe_allow_html=True)
        with h_right:
            st.markdown(
                f'<div style="text-align:right;padding-top:0.1rem;"><span class="{lifecycle_cls}">{lifecycle_label}</span></div>',
                unsafe_allow_html=True,
            )

        st.markdown('<div class="at-rec-divider"></div>', unsafe_allow_html=True)

        col_acc, col_rej = st.columns([1, 1.15], gap="large")

        with col_acc:
            st.markdown(
                '<div class="outcome-header outcome-header-accepted"><span class="dot-accepted"></span>Accepted Approach</div>',
                unsafe_allow_html=True,
            )
            st.markdown(f'<div class="accepted-callout">{final_decision}</div>', unsafe_allow_html=True)
            if rationale:
                st.markdown(
                    f'<div class="rationale-copy"><strong>Rationale:</strong> {rationale}</div>',
                    unsafe_allow_html=True,
                )

            act_cols = st.columns([1, 1])
            with act_cols[0]:
                if source_url:
                    st.link_button("Source Thread", source_url, use_container_width=True)
            with act_cols[1]:
                rec_id = item.get("id", 0)
                st.download_button(
                    "Export ADR (.md)",
                    data=build_adr_fn(item),
                    file_name=f"ADR-{int(rec_id):04d}.md" if isinstance(rec_id, int) else "ADR.md",
                    mime="text/markdown",
                    key=f"adr_dl_{rec_id}",
                    use_container_width=True,
                )

        with col_rej:
            count_pill = f'<span class="count-pill">{len(rejected_alts)}</span>' if rejected_alts else ""
            st.markdown(
                f'<div class="outcome-header outcome-header-rejected"><span class="dot-rejected"></span>Rejected Alternatives {count_pill}</div>',
                unsafe_allow_html=True,
            )
            if not rejected_alts:
                st.caption("No rejected alternatives recorded for this discussion.")
            else:
                for alt in rejected_alts:
                    idea = html.escape(str(alt.get("idea") or "Unnamed alternative"))
                    reason = html.escape(str(alt.get("reason_rejected") or "No rejection rationale recorded."))
                    author = str(alt.get("author") or "").strip()
                    quote = str(alt.get("verbatim_quote") or "").strip()

                    author_html = f'<div class="rejected-meta">author: @{html.escape(author)}</div>' if author else ""
                    quote_html = f'<div class="rejected-quote">"{html.escape(quote)}"</div>' if quote else ""

                    st.markdown(
                        f"""
                        <div class="rejected-item">
                            <div class="rejected-idea-title">{idea}</div>
                            <div class="rejected-reason">{reason}</div>
                            {author_html}
                            {quote_html}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
