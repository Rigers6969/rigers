"""Channel Agent - standalone companion app for The Wayne Factory.

Deliberately a SEPARATE app/process from empire.py's clip pipeline - it does
not share a UI, sidebar, or session with it. Run it on its own:

    streamlit run channel_agent.py --server.port 8502

It generates channel branding (logo, YouTube banner, Instagram profile
picture, description, bio, hashtags) and publishes already-rendered clips to
YouTube/Instagram.

What it does NOT do, because no code can: create your YouTube channel or
Instagram account, or generate OAuth/API credentials for you. Both platforms
require a human to do that manually, once, as a deliberate security
boundary - see the docstrings in publishing.py for exactly what that setup
involves. This app automates everything after that point.
"""
from __future__ import annotations

import os
from pathlib import Path

import streamlit as st

from branding import ClaudeBrandGenerator, OllamaBrandGenerator, prepare_content_for_prompt, save_brand_assets
from publishing import post_to_instagram, upload_to_youtube

APP_DIR = Path(__file__).resolve().parent
BRANDING_OUTPUT_DIR = APP_DIR / "branding_output"
CLIPS_DIR = APP_DIR / "output_clips"  # where empire.py saves finished clips
TRANSCRIPTS_DIR = APP_DIR / "transcripts"  # where empire.py saves transcripts


def main():
    st.set_page_config(page_title="Channel Agent", page_icon=":art:", layout="wide")
    st.title("Channel Agent")
    st.caption("Branding + publishing companion for The Wayne Factory. Runs as its own app.")

    with st.sidebar:
        st.header("Settings")
        engine = st.radio("Engine", ["Ollama (local)", "Claude API"])
        if engine == "Ollama (local)":
            model = st.selectbox("Ollama model", ["llama3", "phi3"])
            ollama_host = st.text_input("Ollama host", value=os.environ.get("OLLAMA_HOST", "http://localhost:11434"))
            anthropic_key = ""
        else:
            model = st.selectbox("Claude model", ["claude-sonnet-5", "claude-opus-5", "claude-haiku-4-5"])
            anthropic_key = st.text_input(
                "Anthropic API key", type="password", value=os.environ.get("ANTHROPIC_API_KEY", "")
            )
            ollama_host = ""

    tab_brand, tab_publish = st.tabs(["Brand Kit", "Publish a Clip"])

    with tab_brand:
        st.write(
            "Generates a channel name (if you don't already have one), logo, YouTube "
            "banner, Instagram profile picture, description, bio, and tags for a "
            "channel/account you've already created manually."
        )

        source_mode = st.radio(
            "Base the brand kit on",
            ["Analyze real video transcripts", "Describe the niche manually"],
        )

        content = ""
        channel_name_hint = ""

        if source_mode == "Analyze real video transcripts":
            transcript_files = sorted(TRANSCRIPTS_DIR.glob("*.txt")) if TRANSCRIPTS_DIR.exists() else []
            if not transcript_files:
                st.warning(
                    f"No transcripts found in {TRANSCRIPTS_DIR.name}/ yet. Run empire.py's pipeline on "
                    "at least one video first - it saves the transcript there automatically."
                )
            else:
                chosen = st.multiselect(
                    "Videos to analyze", [p.name for p in transcript_files], default=[transcript_files[-1].name]
                )
                texts = [
                    (TRANSCRIPTS_DIR / name).read_text(encoding="utf-8")
                    for name in chosen
                ]
                content = prepare_content_for_prompt(texts)
            channel_name_hint = st.text_input(
                "Channel name (leave blank to let the AI suggest one from the content)", value=""
            )
        else:
            channel_name_hint = st.text_input("Channel name", value="The Wayne Factory")
            content = st.text_area(
                "Niche / description", value="Viral short-form clips cut from long-form YouTube videos."
            )

        if st.button("Generate brand kit", type="primary", disabled=not content):
            try:
                with st.spinner("Generating brand kit..."):
                    if engine == "Ollama (local)":
                        generator = OllamaBrandGenerator(model=model, host=ollama_host)
                    else:
                        if not anthropic_key:
                            raise RuntimeError("Enter an Anthropic API key in the sidebar first.")
                        generator = ClaudeBrandGenerator(api_key=anthropic_key, model=model)
                    brand = generator.generate(content, channel_name=channel_name_hint or None)
                    asset_paths = save_brand_assets(brand, BRANDING_OUTPUT_DIR)
                st.session_state["agent_brand"] = brand
                st.session_state["agent_brand_assets"] = asset_paths
            except Exception as exc:
                st.error(str(exc))

        brand = st.session_state.get("agent_brand")
        asset_paths = st.session_state.get("agent_brand_assets")
        if brand and asset_paths:
            st.subheader(brand.channel_name)
            st.write(f"*{brand.tagline}*")

            col1, col2, col3 = st.columns(3)
            with col1:
                st.image(str(asset_paths["logo"]), caption="Logo")
            with col2:
                st.image(str(asset_paths["youtube_banner"]), caption="YouTube banner")
            with col3:
                st.image(str(asset_paths["instagram_profile"]), caption="Instagram profile picture")

            st.text_area("YouTube description", value=brand.youtube_description, height=100, key="agent_yt_desc")
            st.write("**YouTube tags:** " + ", ".join(brand.youtube_tags))
            st.text_area("Instagram bio", value=brand.instagram_bio, height=68, key="agent_ig_bio")
            st.write("**Instagram hashtags:** " + " ".join(brand.instagram_hashtags))

            for label, asset_path in asset_paths.items():
                with open(asset_path, "rb") as f:
                    st.download_button(
                        f"Download {asset_path.name}", f.read(), file_name=asset_path.name, key=f"agent_brand_dl_{label}"
                    )

    with tab_publish:
        st.write(
            "Publish an already-rendered clip to YouTube and/or Instagram. Requires a "
            "one-time manual setup per platform - see the docstrings in publishing.py. "
            "No code can skip this: both platforms require you personally to create "
            "the OAuth/API credentials."
        )

        existing_clips = sorted(CLIPS_DIR.glob("*.mp4")) if CLIPS_DIR.exists() else []
        options = [str(p) for p in existing_clips] + ["Enter a path manually..."]
        choice = st.selectbox("Clip file", options)
        if choice == "Enter a path manually...":
            clip_path_str = st.text_input("Path to clip .mp4", value="")
        else:
            clip_path_str = choice

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**YouTube**")
            yt_title = st.text_input("Title", key="pub_yt_title")
            yt_desc = st.text_area("Description", key="pub_yt_desc")
            yt_secret = st.text_input("client_secret.json path", value="client_secret.json", key="pub_yt_secret")
            yt_privacy = st.selectbox("Privacy", ["private", "unlisted", "public"], key="pub_yt_privacy")
            if st.button("Upload to YouTube", key="pub_yt_upload", disabled=not clip_path_str):
                try:
                    with st.spinner("Uploading to YouTube..."):
                        video_id = upload_to_youtube(
                            Path(clip_path_str), yt_title, yt_desc,
                            client_secret_path=yt_secret, privacy_status=yt_privacy,
                        )
                    st.success(f"Uploaded: https://youtu.be/{video_id}")
                except Exception as exc:
                    st.error(str(exc))
        with col2:
            st.markdown("**Instagram**")
            st.caption("The Graph API fetches the video from a public URL - it can't take a local file directly.")
            ig_caption = st.text_area("Caption", key="pub_ig_caption")
            ig_token = st.text_input("Access token", type="password", key="pub_ig_token")
            ig_user_id = st.text_input("IG Business Account ID", key="pub_ig_user")
            ig_url = st.text_input("Public video URL (already hosted)", key="pub_ig_url")
            if st.button("Post to Instagram", key="pub_ig_post"):
                try:
                    with st.spinner("Posting to Instagram..."):
                        media_id = post_to_instagram(ig_caption, ig_token, ig_user_id, ig_url)
                    st.success(f"Posted: media id {media_id}")
                except Exception as exc:
                    st.error(str(exc))


if __name__ == "__main__":
    main()
