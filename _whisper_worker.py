"""Isolated Whisper transcription worker for The Wayne Factory.

Run as a subprocess (not imported) so a transcription crash or OOM never
takes down the Streamlit process. Writes progress lines to stdout and the
final transcript as JSON to the given output path.

Usage: python _whisper_worker.py <video_path> <model_size> <output_json_path>
"""
import json
import sys


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: _whisper_worker.py <video_path> <model_size> <output_json_path>", file=sys.stderr)
        return 2

    video_path, model_size, out_path = sys.argv[1], sys.argv[2], sys.argv[3]

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("faster-whisper is not installed. Run: pip install faster-whisper", file=sys.stderr)
        return 1

    print(f"Loading Whisper model '{model_size}'...", flush=True)
    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    print("Transcribing...", flush=True)
    segments_iter, info = model.transcribe(video_path, beam_size=5, vad_filter=True)

    duration = info.duration or 0.0
    segments = []
    for seg in segments_iter:
        text = seg.text.strip()
        if not text:
            continue
        segments.append({"start": seg.start, "end": seg.end, "text": text})
        pct = (seg.end / duration * 100) if duration else 0.0
        print(f"PROGRESS {seg.end:.1f}/{duration:.1f}s ({pct:.0f}%)", flush=True)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"language": info.language, "duration": duration, "segments": segments}, f)

    print(f"Done: {len(segments)} segment(s), {duration:.1f}s total.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
