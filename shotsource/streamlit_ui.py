"""Streamlit UI for the media finder, embedded as a tab inside studio.py
(the combined dashboard). Kept separate from pipeline.py so the plain CLI
(python -m shotsource.cli) doesn't need streamlit installed at all.
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import streamlit as st

from .pipeline import run_pipeline

DEFAULT_OUTPUT_DIR = "./shot_media_output"


def render_media_finder_tab():
    st.caption(
        "Give it a shot list; it queries Openverse, Wikimedia Commons, the Library of "
        "Congress, archive.org, Pexels, Pixabay, and Unsplash (via their public APIs - "
        "no scraping), quality-filters the results, and keeps the top matches per shot."
    )

    shots_text = st.text_area(
        "Shot list - one description per line",
        value="1970s university cafeteria\ncrowded dinner table candlelight",
        height=150,
    )
    col1, col2 = st.columns(2)
    with col1:
        output_dir = st.text_input("Output directory", value=DEFAULT_OUTPUT_DIR, key="media_finder_output_dir_input")
    with col2:
        config_path = st.text_input(
            "Config YAML (optional override)", value="", key="media_finder_config_path",
            help="Leave blank to use shotsource/config.default.yaml as-is.",
        )

    if st.button("Find media", type="primary", disabled=not shots_text.strip()):
        shots_path = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
                f.write(shots_text)
                shots_path = f.name
            with st.spinner("Querying sources and quality-filtering results - this can take a while..."):
                run_pipeline(shots_path, config_path or None, output_dir)
            st.session_state["media_finder_output_dir"] = output_dir
        except Exception as exc:
            st.error(str(exc))
        finally:
            if shots_path:
                Path(shots_path).unlink(missing_ok=True)

    output_dir_state = st.session_state.get("media_finder_output_dir")
    if not output_dir_state:
        return

    output_dir_path = Path(output_dir_state)
    manifest_path = output_dir_path / "manifest.csv"
    if not manifest_path.exists():
        return

    import pandas as pd  # streamlit already depends on pandas

    df = pd.read_csv(manifest_path)
    if df.empty:
        st.warning("No media survived the quality filter for any shot - check rejections.csv below.")
    else:
        st.success(f"Kept {len(df)} media file(s) across {df['shot_id'].nunique()} shot(s).")
        st.dataframe(df[["shot_id", "shot_description", "rank", "source", "license", "final_score"]])

        for shot_id, group in df.groupby("shot_id"):
            st.markdown(f"**{shot_id}: {group.iloc[0]['shot_description']}**")
            cols = st.columns(len(group))
            for col, (_, row) in zip(cols, group.iterrows()):
                with col:
                    if Path(row["local_path"]).exists():
                        st.image(row["local_path"], caption=f"{row['source']} · {row['final_score']:.2f}")

        zip_path = shutil.make_archive(str(output_dir_path), "zip", root_dir=output_dir_path)
        with open(zip_path, "rb") as f:
            st.download_button("Download all media + manifest (.zip)", f.read(), file_name=Path(zip_path).name)

    rejections_path = output_dir_path / "rejections.csv"
    if rejections_path.exists():
        with open(rejections_path, "rb") as f:
            st.download_button("Download rejections.csv", f.read(), file_name="rejections.csv")
