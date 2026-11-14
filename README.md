# AutoSage — Multimodal Chat Demo

React + TypeScript + Vite + Tailwind frontend, with a FastAPI mock API. The UI follows the approved [plan and mockups](UI/PLAN.md).

## Run locally

Requires Python 3.11+ and Node.js 22.12+ (or Node.js 20.19+).

From the repository root, in PowerShell:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r backend/requirements.txt
.venv/Scripts/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open [AutoSage locally](http://127.0.0.1:5173). Vite proxies `/api` to FastAPI on port 8000; keep both processes running. Use one backend worker. No API key is needed. All fonts and assets are local; no CDN is required after dependency installation.

## Done

- Responsive white-and-teal chat, recent conversations, new chats, and explicitly labeled example replies.
- Text, image/audio/video uploads, microphone audio recording, camera video recording, review before attachment, and inline playback.
- Real device permission, cancel/error states, runtime recording-format negotiation, device cleanup, failed-send draft preservation, and a persistent brake-warning example banner.
- Multipart API with atomic upload validation, five files per message, 25 MB per file, 50 MB combined, and 10,000 text characters.
- Audio recording stops after two minutes; video stops after one minute. Both stop when exceeding the file-size limit.

## Checks

```powershell
# Repository root
.venv/Scripts/python -m pytest backend/tests -q

# frontend (both servers must be running)
npm run build
npx playwright install chromium
npm run test:e2e
```

Browser tests use synthetic camera/microphone streams and cover recording, review, playback, upload, safety examples, mobile layout, denied permissions, and backend failures. Manually verify real-device permissions, recording quality, and playback on your target browser. Recording needs localhost or HTTPS; a plain HTTP LAN address will not support device access. When recording is unsupported or access is denied, upload remains available.

## Known limitations and next work

This is the selected **mock UI phase**, not the broader agent implementation in `PROJECT_PLAN.md`. No Gemini/Gemma, Bayesian diagnosis, real sensors, transcription, media analysis, authentication, database, or deployment is included. All assistant messages and activity steps are examples. The symptom keyword check is a demonstration, not a comprehensive safety system.

Chats and attachment bytes live only in process memory. Backend restart removes them and restores three sample text conversations. Uploads are checked by declared MIME type and size; this local demo does not decode, scan, transcode, or persist them. Storage is not designed for public or multiuser hosting. Browser-supported JPEG/PNG/WebP/GIF images, WebM/MP4/QuickTime/Ogg video, and WebM/Ogg/WAV/MP4/MP3/AAC audio can be attached; playback depends on browser codec support.

Draft attachments belong to the active conversation and are cleared when switching chats. Initial sample conversations contain text only; attach your own media to exercise previews rather than preloading user photos. Camera permission currently requires both camera and microphone.

Next: the separately scoped real diagnostic workflow, persistence/authentication, and deployment if requested. See [UI/PLAN.md](UI/PLAN.md) for this phase's contracts and defaults.
