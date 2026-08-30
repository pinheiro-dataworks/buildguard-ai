"""Renan-standard visual tokens and CSS injection (docs/design/UI_DESIGN_SPEC.md).

Colors and the sidebar treatment come from `docs/design/renan-standard.png`
-- the prototype HTML (`docs/design/prototype-inspiration.html`) is layout
inspiration only, its blue color system is never used. Risk-band colors
are adapted from the prototype's own accessible palette (dropped to three
bands, matching `buildguard.models.thresholds.risk_band`'s low/medium/high
-- this project's thresholds never produce a fourth "critical" band).
"""

from __future__ import annotations

import streamlit as st

SIDEBAR_BG = "#141414"
SIDEBAR_TEXT = "#E9E5D8"
SIDEBAR_TEXT_DIM = "#8A8676"
SIDEBAR_BORDER = "#C9C4B0"
CANVAS_BG = "#F5F3EA"
SURFACE = "#FFFFFF"
INK = "#16171A"
ACCENT_WARM = "#E8531F"
ACCENT_COOL = "#2F8FE0"

RISK_COLORS: dict[str, tuple[str, str]] = {
    # band -> (ink, soft background)
    "low": ("#25794F", "#E3F3EA"),
    "medium": ("#A9700A", "#FBF0DA"),
    "high": ("#B14A1E", "#FBE7DC"),
}

GITHUB_URL = "https://github.com/pinheiro-dataworks/buildguard-ai"


def risk_badge_html(band: str, label: str | None = None) -> str:
    ink, soft = RISK_COLORS.get(band, RISK_COLORS["medium"])
    text = label or band.upper()
    return (
        f'<span style="display:inline-flex;align-items:center;gap:6px;'
        f"font-size:11px;font-weight:700;padding:4px 10px;border-radius:20px;"
        f'text-transform:uppercase;letter-spacing:0.03em;background:{soft};color:{ink};">'
        f'<span style="width:6px;height:6px;border-radius:50%;background:{ink};"></span>'
        f"{text}</span>"
    )


def inject_css() -> None:
    st.markdown(
        f"""
        <style>
        .stApp {{ background-color: {CANVAS_BG}; }}
        [data-testid="stSidebar"] {{
            background-color: {SIDEBAR_BG};
        }}
        [data-testid="stSidebar"] * {{
            color: {SIDEBAR_TEXT};
        }}
        [data-testid="stSidebar"] .stButton > button {{
            width: 100%;
            text-align: left;
            background-color: transparent;
            color: {SIDEBAR_TEXT};
            border: 1px solid {SIDEBAR_BORDER};
            border-radius: 6px;
            padding: 0.5rem 0.9rem;
            margin-bottom: 0.4rem;
            font-weight: 500;
        }}
        [data-testid="stSidebar"] .stButton > button:hover {{
            border-color: {ACCENT_WARM};
            color: {ACCENT_WARM};
        }}
        [data-testid="stSidebar"] .stButton > button:focus:not(:active) {{
            border-color: {ACCENT_WARM};
            color: {SIDEBAR_TEXT};
        }}
        [data-testid="stSidebar"] .stButton > button[kind="primary"] {{
            border-color: {ACCENT_WARM} !important;
            background-color: rgba(232, 83, 31, 0.22) !important;
            color: {SIDEBAR_TEXT} !important;
            font-weight: 700;
        }}
        .bg-sidebar-logo {{
            text-align: center;
            margin: 0.2rem 0 0.4rem 0;
        }}
        .bg-sidebar-logo img {{
            max-width: 140px;
            width: 100%;
            height: auto;
        }}
        .bg-sidebar-title {{
            color: {SIDEBAR_TEXT};
            font-size: 1.15rem;
            font-weight: 800;
            text-align: center;
            margin: 0.3rem 0 1.1rem 0;
        }}
        .bg-sidebar-footer {{
            color: {SIDEBAR_TEXT_DIM};
            font-size: 0.78rem;
            line-height: 1.6;
            text-align: center;
        }}
        .bg-sidebar-footer a {{
            color: {SIDEBAR_TEXT_DIM};
            text-decoration: underline;
        }}
        /* The logo is now a plain <img>, not st.image, specifically to
           avoid this -- but keep it belt-and-suspenders in case any
           other sidebar image is ever added with st.image(). */
        [data-testid="stSidebar"] [data-testid="StyledFullScreenButton"],
        [data-testid="stSidebar"] button[title="View fullscreen"] {{
            display: none;
        }}
        .bg-card {{
            background-color: {SURFACE};
            border-radius: 10px;
            padding: 1.1rem 1.3rem;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08);
            margin-bottom: 0.9rem;
        }}
        .bg-kpi-label {{
            color: #6B6A63;
            font-size: 0.78rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.03em;
        }}
        .bg-kpi-value {{
            color: {INK};
            font-size: 1.7rem;
            font-weight: 800;
            margin-top: 0.15rem;
        }}
        .bg-kpi-sub {{
            color: #8A8676;
            font-size: 0.78rem;
            margin-top: 0.1rem;
        }}
        .bg-disclaimer {{
            background-color: #FBF0DA;
            color: #6E5108;
            border: 1px solid #E8D5A0;
            border-radius: 8px;
            padding: 0.7rem 1rem;
            font-size: 0.85rem;
            margin: 0.6rem 0 1rem 0;
        }}
        h1, h2, h3 {{ color: {INK}; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def kpi_card(label: str, value: str, sub: str | None = None) -> str:
    sub_html = f'<div class="bg-kpi-sub">{sub}</div>' if sub else ""
    return (
        f'<div class="bg-card"><div class="bg-kpi-label">{label}</div>'
        f'<div class="bg-kpi-value">{value}</div>{sub_html}</div>'
    )


CAUSALITY_DISCLAIMER = (
    "Feature attribution explains the model prediction; it does not establish causality."
)
DECISION_SUPPORT_DISCLAIMER = (
    "BuildGuard AI is decision support, not an autonomous decision-maker -- "
    "every estimate here is a probability or point forecast for a human reviewer "
    "to weigh, never a verdict."
)
