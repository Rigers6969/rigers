"""Dashboard - stats + greeting app for The Wayne Factory.

Deliberately a SEPARATE app/process from empire.py and channel_agent.py,
same pattern as channel_agent.py. Run it on its own:

    streamlit run dashboard.py --server.port 8900

Shows an animated "Good Morning/Afternoon/Evening, Bruce" splash (dark
theme, live Albania clock, drifting bat animation), then pulls and
displays real statistics from your YouTube channel and Instagram account.

Needs your own credentials to fetch real data - see analytics.py's
docstring for exactly how to get a YouTube API key (much simpler than the
OAuth flow publishing.py needs for uploading - read-only stats just need a
plain API key) and how to reuse the Instagram Graph API access token you
already set up for channel_agent.py's publishing.
"""
from __future__ import annotations

import os

import streamlit as st

import ui_theme
from analytics import StatsFetchError, fetch_instagram_stats, fetch_youtube_stats


def main():
    st.set_page_config(page_title="Dashboard", page_icon=":bar_chart:", layout="wide")

    if not ui_theme.show_splash_gate(app_name="Bruce"):
        return

    ui_theme.apply_dark_theme()
    ui_theme.render_bat_swarm_background()

    st.title("Dashboard")
    st.caption("Live stats for your YouTube channel and Instagram account.")

    with st.sidebar:
        ui_theme.render_clock_widget()
        st.header("YouTube")
        yt_channel_id = st.text_input("Channel ID", value=os.environ.get("YOUTUBE_CHANNEL_ID", ""))
        yt_api_key = st.text_input(
            "API key", type="password", value=os.environ.get("YOUTUBE_API_KEY", "")
        )
        st.header("Instagram")
        ig_user_id = st.text_input("Business Account ID", value=os.environ.get("IG_USER_ID", ""))
        ig_token = st.text_input(
            "Access token", type="password", value=os.environ.get("IG_ACCESS_TOKEN", "")
        )
        refresh_clicked = st.button("Refresh stats", type="primary")

    if refresh_clicked or "dashboard_stats" not in st.session_state:
        stats = {"youtube": None, "instagram": None, "errors": []}
        if yt_channel_id and yt_api_key:
            try:
                stats["youtube"] = fetch_youtube_stats(yt_channel_id, yt_api_key)
            except (StatsFetchError, Exception) as exc:
                stats["errors"].append(f"YouTube: {exc}")
        if ig_user_id and ig_token:
            try:
                stats["instagram"] = fetch_instagram_stats(ig_user_id, ig_token)
            except (StatsFetchError, Exception) as exc:
                stats["errors"].append(f"Instagram: {exc}")
        st.session_state["dashboard_stats"] = stats

    stats = st.session_state.get("dashboard_stats") or {}
    for err in stats.get("errors", []):
        st.error(err)

    if not yt_channel_id and not ig_user_id:
        st.info(
            "Enter your YouTube channel ID/API key and/or Instagram credentials in the "
            "sidebar, then click Refresh stats."
        )

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("YouTube")
        yt = stats.get("youtube")
        if yt:
            st.caption(yt["channel_title"])
            ui_theme.render_stat_card(
                "Subscribers", yt["subscriber_count"], icon="\U0001F465",
                note="hidden by channel owner" if yt["subscriber_count_hidden"] else "",
            )
            ui_theme.render_stat_card("Total views", yt["view_count"], icon="\U0001F441")
            ui_theme.render_stat_card("Videos", yt["video_count"], icon="\U0001F3AC")
        else:
            st.caption("No data yet.")
    with col2:
        st.subheader("Instagram")
        ig = stats.get("instagram")
        if ig:
            st.caption(f"@{ig['username']}")
            ui_theme.render_stat_card("Followers", ig["followers_count"], icon="❤️")
            ui_theme.render_stat_card("Posts", ig["media_count"], icon="\U0001F4F8")
        else:
            st.caption("No data yet.")


if __name__ == "__main__":
    main()
