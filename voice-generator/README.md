# Voice Generator

Paste text, pick a voice, get an MP3 - that's all. Standalone: this folder
doesn't need anything else from the repo.

**Run:** double-click `start.bat` (it starts the app and opens
http://localhost:5002 in your browser), or run `python voice_app.py`.

First time only: `pip install -r requirements.txt`. Long texts also need
ffmpeg (already installed if the video apps work).

Every MP3 is saved in `output/`. Voices: Ryan and Thomas (British, male) -
add more in `VOICES` at the top of `voice_engine.py`.
