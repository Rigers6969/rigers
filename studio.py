"""Content Studio - combines the psychology voiceover generator and the
shot-list media finder into a single dashboard, unlike every other app in
this project (empire.py, channel_agent.py, dashboard.py, voice_generator.py)
which deliberately run standalone. Run it on its own:

    streamlit run studio.py --server.port 8505

Each tool still works standalone too - voice_generator.py and
shot_media_cli.py haven't gone anywhere. This just gives both a shared
window when you want to write a voiceover and source its shots' media in
one sitting.
"""
from __future__ import annotations

import streamlit as st

import ui_theme
from shotsource.streamlit_ui import render_media_finder_tab
from voice_generator import render_voiceover_tab


def main():
    st.set_page_config(page_title="Content Studio", page_icon=":clapper:", layout="wide")

    if not ui_theme.show_splash_gate(app_name="Batman"):
        return

    st.title("Content Studio")
    st.caption("Voiceover generation and openly-licensed media sourcing, in one dashboard.")

    # render_voiceover_tab() already renders the sidebar clock + its own
    # settings - no need to duplicate it here.
    tab_voice, tab_media = st.tabs(["Voiceover Generator", "Media Finder"])
    with tab_voice:
        render_voiceover_tab()
    with tab_media:
        render_media_finder_tab()


if __name__ == "__main__":
    main()
