"""Shared dark 'Wayne Factory' visual theme for both Streamlit apps.

Renders a black theme with a gold-glow bat emoji (an original look, not
DC's bat-signal emblem or any character artwork - trademark/copyright risk
to avoid) plus a live, client-side ticking clock for a configurable
timezone (defaults to Albania - Europe/Tirane).

If you have your own licensed image you want as the actual background,
drop it at assets/background.jpg and it's used automatically in place of
the plain black background - nothing else needs to change.
"""
from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

APP_DIR = Path(__file__).resolve().parent
ASSETS_DIR = APP_DIR / "assets"
CUSTOM_BACKGROUND_PATH = ASSETS_DIR / "background.jpg"

DEFAULT_TIMEZONE = "Europe/Tirane"
DEFAULT_CLOCK_LABEL = "Tirana"


def _background_image_css() -> str:
    if CUSTOM_BACKGROUND_PATH.exists():
        data = base64.b64encode(CUSTOM_BACKGROUND_PATH.read_bytes()).decode("ascii")
        return f"background-image: url('data:image/jpeg;base64,{data}'); background-size: cover; background-position: center; background-attachment: fixed;"
    return ""


def apply_dark_theme():
    st.markdown(
        f"""
        <style>
        .stApp {{
            background-color: #000000;
            {_background_image_css()}
        }}
        .stApp, .stApp p, .stApp label, .stApp span, .stApp li {{
            color: #F0F0F0;
        }}
        section[data-testid="stSidebar"] {{
            background-color: rgba(0,0,0,0.9);
        }}
        header[data-testid="stHeader"] {{
            background-color: #000000;
        }}
        .stButton > button {{
            background-color: #F2C230;
            color: #000000;
            font-weight: bold;
            border: none;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _clock_html(element_id: str, timezone: str) -> str:
    # Each caller renders inside its own isolated iframe (components.html),
    # so a fixed function name is fine - no cross-widget collision risk.
    # (element_id is NOT usable in the name itself: ids like "wf-sidebar-clock"
    # contain hyphens, which are invalid in JS identifiers and would throw a
    # silent syntax error, breaking the whole script.)
    return f"""
    <script>
    function tick() {{
        const now = new Date();
        const timeOpts = {{ timeZone: "{timezone}", hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }};
        const timeStr = new Intl.DateTimeFormat('en-GB', timeOpts).format(now);
        const el = document.getElementById("{element_id}");
        if (el) el.innerText = timeStr;
    }}
    tick();
    setInterval(tick, 1000);
    </script>
    """


def render_clock_widget(timezone: str = DEFAULT_TIMEZONE, label: str = DEFAULT_CLOCK_LABEL, height: int = 110):
    """A large, animated, persistent live clock - use in the sidebar so the
    time is impossible to miss anywhere in the app, not just on the splash
    screen."""
    components.html(
        f"""
        <style>
        @keyframes wf-pulse-border {{
            0%, 100% {{ box-shadow: 0 0 8px 2px rgba(242,194,48,0.4); border-color: #F2C230; }}
            50% {{ box-shadow: 0 0 22px 6px rgba(242,194,48,0.9); border-color: #FFE9A8; }}
        }}
        #wf-clock-box {{
            text-align:center; padding:14px 8px; background:#000; border-radius:10px;
            border:2px solid #F2C230; animation: wf-pulse-border 2s ease-in-out infinite;
        }}
        #wf-sidebar-clock {{
            font-family:'Courier New', monospace; font-size:38px; font-weight:bold;
            color:#F2C230; letter-spacing:3px;
        }}
        </style>
        <div id="wf-clock-box">
            <div id="wf-sidebar-clock"></div>
            <div style="font-size:12px; color:#999; margin-top:4px;">{label} time</div>
        </div>
        {_clock_html("wf-sidebar-clock", timezone)}
        """,
        height=height,
    )


def render_splash_banner(app_name: str, timezone: str = DEFAULT_TIMEZONE, clock_label: str = DEFAULT_CLOCK_LABEL):
    """Big greeting banner: 'Good Morning/Afternoon/Evening/Night, {app_name}'
    computed from the current time in `timezone`, plus a live clock."""
    components.html(
        f"""
        <style>
        @keyframes wf-bat-glow {{
            0%, 100% {{ text-shadow: 0 0 30px #F2C230, 0 0 60px #F2C230; transform: scale(1); }}
            50% {{ text-shadow: 0 0 50px #FFE9A8, 0 0 100px #F2C230; transform: scale(1.08); }}
        }}
        @keyframes wf-fade-in {{
            from {{ opacity: 0; transform: translateY(-10px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        @keyframes wf-clock-pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.6; }}
        }}
        #wf-bat {{ font-size:90px; display:inline-block; animation: wf-bat-glow 2.5s ease-in-out infinite; }}
        #wf-greeting {{
            font-size:40px; font-weight:bold; color:#F2C230; margin-top:8px; letter-spacing:1px;
            animation: wf-fade-in 1s ease-out;
        }}
        #wf-clock {{
            font-size:44px; color:#fff; margin-top:14px; letter-spacing:4px; font-family:'Courier New', monospace;
            font-weight:bold; animation: wf-clock-pulse 2s ease-in-out infinite;
        }}
        </style>
        <div style="background:#000; text-align:center; padding:36px 16px; border-radius:10px;
                    margin-bottom:16px; box-shadow: 0 0 40px rgba(242,194,48,0.15) inset;">
            <div id="wf-bat">&#129415;</div>
            <div id="wf-greeting"></div>
            <div id="wf-clock"></div>
            <div style="font-size:14px; color:#888; margin-top:4px;">{clock_label} time</div>
        </div>
        <script>
        function wf_tick() {{
            const now = new Date();
            const timeOpts = {{ timeZone: "{timezone}", hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false }};
            const timeStr = new Intl.DateTimeFormat('en-GB', timeOpts).format(now);
            const hourOpts = {{ timeZone: "{timezone}", hour: 'numeric', hour12: false }};
            const hour = parseInt(new Intl.DateTimeFormat('en-GB', hourOpts).format(now));
            let greeting;
            if (hour < 5) greeting = "Good Night, {app_name}";
            else if (hour < 12) greeting = "Good Morning, {app_name}";
            else if (hour < 18) greeting = "Good Afternoon, {app_name}";
            else greeting = "Good Evening, {app_name}";
            document.getElementById('wf-greeting').innerText = greeting;
            document.getElementById('wf-clock').innerText = timeStr;
        }}
        wf_tick();
        setInterval(wf_tick, 1000);
        </script>
        """,
        height=340,
    )


def show_splash_gate(
    app_name: str = "Batman",
    timezone: str = DEFAULT_TIMEZONE,
    clock_label: str = DEFAULT_CLOCK_LABEL,
    session_key: str = "wf_entered",
) -> bool:
    """Renders the splash banner and an Enter button until dismissed for this
    session. Call at the very top of main(), before any other UI, and stop
    rendering the rest of the page if this returns False:

        if not ui_theme.show_splash_gate():
            return
    """
    apply_dark_theme()
    if st.session_state.get(session_key):
        return True
    render_splash_banner(app_name, timezone, clock_label)
    _, center, _ = st.columns([1, 1, 1])
    with center:
        if st.button("Enter", key=f"{session_key}_button", type="primary", use_container_width=True):
            st.session_state[session_key] = True
            st.rerun()
    return False
