"""Streamlit entry point (Section 30/33).

A custom sidebar router, not `st.navigation()`: `docs/design/UI_DESIGN_SPEC.md`
requires an exact sidebar order (logo, then project name, then bordered
rectangular nav buttons, then a version/GitHub footer). `st.navigation()`
was tried first and rejected -- its sidebar nav widget always renders at
a fixed position, regardless of where surrounding `st.sidebar` calls are
placed in the script, so the logo/title could not be positioned above it
as the spec requires. A plain `st.sidebar.button()` per page, styled via
CSS and tracked in `st.session_state`, gives full control over both order
and appearance.

Page content lives one file per page under `page_modules/` (not
Section 33's suggested `pages/` -- that literal directory name triggers
Streamlit's legacy auto-discovery regardless of navigation approach,
confirmed empirically: it produced a second, unstyled nav list stacked on
top of this one). Each file exposes a single `render()` function.
"""

from __future__ import annotations

import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

import streamlit as st  # noqa: E402

import buildguard  # noqa: E402
import theme  # noqa: E402
from page_modules import (  # noqa: E402
    about_governance,
    executive_overview,
    model_health,
    model_performance,
    project_diagnostic,
    scenario_simulator,
)

st.set_page_config(
    page_title="BuildGuard AI",
    page_icon="\U0001f3d7️",
    layout="wide",
    initial_sidebar_state="expanded",
)
theme.inject_css()

PAGES = {
    "Executive Overview": executive_overview,
    "Project Diagnostic": project_diagnostic,
    "Scenario Simulator": scenario_simulator,
    "Model Performance": model_performance,
    "Model Health": model_health,
    "About / Governance": about_governance,
}

if "active_page" not in st.session_state:
    st.session_state["active_page"] = next(iter(PAGES))

with st.sidebar:
    st.image(str(APP_DIR.parent / "assets" / "brand" / "logo_renan_ds.png"), width=140)
    st.markdown('<div class="bg-sidebar-title">BuildGuard AI</div>', unsafe_allow_html=True)

    for page_name in PAGES:
        is_active = st.session_state["active_page"] == page_name
        if st.button(
            page_name,
            key=f"nav_{page_name}",
            type="primary" if is_active else "secondary",
            use_container_width=True,
        ):
            st.session_state["active_page"] = page_name
            st.rerun()

    st.markdown("<div style='min-height:3rem;'></div>", unsafe_allow_html=True)
    st.markdown(
        f'<div class="bg-sidebar-footer">v{buildguard.__version__}<br>'
        f'<a href="{theme.GITHUB_URL}" target="_blank">GitHub</a></div>',
        unsafe_allow_html=True,
    )

PAGES[st.session_state["active_page"]].render()
