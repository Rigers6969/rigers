"""Face-tracking crop for vertical clips: follow the person who is talking instead of always cutting the middle.

How it works: about 5 pictures a second are checked for faces (OpenCV, on the CPU, small size so it's fast).
Faces (OpenCV's YuNet detector) are kept as "tracks" by where they sit. The one whose mouth area moves the most over the last
~1.5 s is taken as the speaker. The camera holds still on the speaker and glides (0.35 s) to the other
person when the speaker changes - never jittery, never faster than one move every 1.5 s.

Returns an ffmpeg expression for the crop's x position, or None (then the clip uses the normal centre crop).
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Optional

import numpy as np

FPS = 5            # pictures checked per second
SAMPLE_W = 480     # they are checked at this width
MIN_HOLD = 1.5     # seconds the camera stays before it may move again
GLIDE = 0.35       # seconds a camera move takes
SWITCH_RATIO = 1.35  # the other face must be this much more "talking" to switch


def _frames(source: Path, start: float, length: float) -> tuple[np.ndarray, int, int]:
    probe = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                            "-of", "csv=s=x:p=0", str(source)], capture_output=True, text=True, timeout=30)
    w, h = (int(v) for v in probe.stdout.strip().split("x")[:2])
    sh = int(round(SAMPLE_W * h / w / 2) * 2)
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-i", str(source),
                          "-vf", f"fps={FPS},scale={SAMPLE_W}:{sh},format=gray", "-f", "rawvideo", "-"],
                         capture_output=True, timeout=max(60, length * 4)).stdout
    n = len(raw) // (SAMPLE_W * sh)
    return np.frombuffer(raw[: n * SAMPLE_W * sh], np.uint8).reshape(n, sh, SAMPLE_W), w, h


MODEL = Path(__file__).resolve().parent / "models" / "face_yunet_2023mar.onnx"
MODEL_URL = ("https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/"
             "face_detection_yunet/face_detection_yunet_2023mar.onnx")


def make_detector(w: int, h: int):
    """A function picture -> [(x, y, w, h)] faces. OpenCV's YuNet AI detector (model downloaded once, ~0.2 MB);
    falls back to the old Haar detector on OpenCV versions that still have it."""
    import cv2

    if hasattr(cv2, "FaceDetectorYN"):
        try:
            if not MODEL.exists() or MODEL.stat().st_size < 100_000:
                import urllib.request

                MODEL.parent.mkdir(exist_ok=True)
                tmp = MODEL.with_suffix(".part")
                urllib.request.urlretrieve(MODEL_URL, tmp)
                tmp.replace(MODEL)
            yn = cv2.FaceDetectorYN.create(str(MODEL), "", (w, h), 0.6)

            def detect(gray):
                _, faces = yn.detect(cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR))
                return [tuple(int(v) for v in f[:4]) for f in (faces if faces is not None else [])]
            return detect
        except Exception:
            pass
    if hasattr(cv2, "CascadeClassifier"):
        haar = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        return lambda gray: [tuple(f) for f in haar.detectMultiScale(gray, scaleFactor=1.15, minNeighbors=5,
                                                                         minSize=(int(w * 0.06), int(w * 0.06)))]
    raise ImportError("no face detector in this OpenCV")


def speaker_path(frames: np.ndarray, detect=None) -> Optional[list[tuple[float, float]]]:
    """[(time, face centre x as 0..1)] for each sample, following the speaker; None if there are hardly any faces."""
    n, H, W = frames.shape
    detect = detect or make_detector(W, H)
    tracks: list[dict] = []          # {"x": centre 0..1, "size": face width 0..1, "act": [activity per sample]}
    seen = 0
    for i in range(n):
        faces = [f for f in detect(frames[i]) if f[2] >= W * 0.04]
        for tr in tracks:
            tr["act"].append(0.0)
        if len(faces):
            seen += 1
        for (fx, fy, fw, fh) in faces:
            cx = (fx + fw / 2) / W
            tr = min(tracks, key=lambda t: abs(t["x"] - cx), default=None)
            if tr is None or abs(tr["x"] - cx) > 0.12:
                tr = {"x": cx, "size": fw / W, "act": [0.0] * (i + 1)}
                tracks.append(tr)
            tr["x"] = 0.8 * tr["x"] + 0.2 * cx
            tr["size"] = 0.8 * tr["size"] + 0.2 * fw / W
            if i:  # mouth area movement since the last picture = "is talking"
                y0, y1, x0, x1 = fy + fh // 2, min(H, fy + fh + fh // 4), fx + fw // 5, fx + fw - fw // 5
                a = np.abs(frames[i, y0:y1, x0:x1].astype(np.int16) - frames[i - 1, y0:y1, x0:x1].astype(np.int16))
                tr["act"][-1] = float(a.mean()) + 2.0 * tr["size"]  # bigger faces win ties
    if n == 0 or seen < n * 0.4 or not tracks:
        return None
    tracks = [t for t in tracks if sum(1 for a in t["act"] if a > 0) >= max(2, n * 0.08)] or tracks
    win = int(FPS * 1.5)
    cur = max(tracks, key=lambda t: sum(t["act"][:win]))
    last_move, path = 0.0, []
    for i in range(n):
        t = i / FPS
        score = lambda tr: sum(tr["act"][max(0, i - win + 1): i + 1])
        best = max(tracks, key=score)
        if best is not cur and t - last_move >= MIN_HOLD and score(best) > SWITCH_RATIO * max(score(cur), 1e-6):
            cur, last_move = best, t
        path.append((t, cur["x"]))
    return path


def x_expression(path: list[tuple[float, float]], offset: float = 0.0) -> str:
    """ffmpeg crop x for a 9:16 window that holds on the speaker and glides between speakers."""
    holds = []  # [(time, x)] - a new hold only when the target really moves
    for t, x in path:
        if not holds or abs(x - holds[-1][1]) > 0.08:
            holds.append((t, x))
    win = "ih*9/16"
    pos = lambda x: f"min(max({x:.4f}*iw-{win}/2,0),iw-{win})"
    T = f"(t-{offset:.3f})" if offset else "t"
    expr = pos(holds[-1][1])
    for (t0, x0), (t1, x1) in reversed(list(zip(holds, holds[1:]))):
        glide = f"{pos(x0)}+({pos(x1)}-{pos(x0)})*({T}-{t1:.3f})/{GLIDE}"
        expr = f"if(lt({T},{t1:.3f}),{pos(x0)},if(lt({T},{t1 + GLIDE:.3f}),{glide},{expr}))"
    if len(holds) == 1:
        expr = pos(holds[0][1])
    return expr


def track_expr(source: Path, start: float, length: float, offset: float = 0.0) -> Optional[str]:
    """The crop x expression for this part of the video, or None (no faces / portrait video / OpenCV missing)."""
    try:
        frames, w, h = _frames(Path(source), start, length)
    except Exception:
        return None
    if w <= h * 1.05:  # already vertical: nothing to follow
        return None
    try:
        path = speaker_path(frames)
    except ImportError:
        return None
    return x_expression(path, offset) if path else None
