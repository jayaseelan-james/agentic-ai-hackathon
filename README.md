# AutoSage — Gemini Diagnostic Chat

React + TypeScript + Vite + Tailwind UI with a FastAPI backend and real Gemini investigations. Supports text, images, microphone recordings, camera video and gallery uploads, with grounded references and visible tool activity.

## Run locally

Requires Python 3.11+ and Node.js 22.12+ (or 20.19+). PowerShell commands from the repository root:

```powershell
python -m venv .venv
.venv/Scripts/python -m pip install -r backend/requirements.txt
Copy-Item .env.example .env
```

Edit the ignored root `.env` and set `GEMINI_API_KEY` to your Google AI Studio key. Keep the key in the backend only. If `.env` already exists, keep it and edit it instead of copying over it. Environment variables take precedence over `.env` values.

`GEMINI_MODEL` defaults to `gemini-4-carbon`, selected for reasoning and multimodal investigation. This model and its Google Search grounding require account access and may incur charges; use a compatible model override if needed. There is no silent fallback to canned replies or another model.

```powershell
.venv/Scripts/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open [AutoSage locally](http://127.0.0.1:5173). Vite proxies `/api` to port 8000. Keep both servers running and use one backend worker. The local app contains no API keys or remote fonts. Restart the backend after changing configuration.

## Diagnostic workflow

1. Start a chat and optionally enter vehicle make/model/year. The default is “Vehicle details not provided.” A model-specific specification requires confirmed vehicle details and relevant documentation.
2. Submit text and/or media. FastAPI returns `202` with the saved user message, immediate safety status, and a processing assistant message. The UI polls the incident for the result.
3. Gemini can use built-in Google Search and URL context, plus validated `get_vehicle_profile`, `create_mechanic_report`, `list_available_sensors`, `read_vehicle_sensors`, and `read_sensor_history` functions. The activity panel shows real actions, arguments and returned data, not hidden reasoning. Sources are mapped from returned annotations; Google Search suggestions appear in a sandboxed frame.
4. The chat asks one targeted follow-up question at a time, using each answer and relevant tool evidence to narrow the problem. It avoids listing possible causes upfront. When the evidence supports a leading explanation, it connects that explanation to the observations and gives a safe next action; unresolved uncertainty is referred for inspection rather than forced into a definitive diagnosis. Model claims remain unconfirmed. A report can be copied when the agent creates a mechanic handoff.
5. A failed investigation exposes a retry button that reuses the saved message and attachments. Network-submission retries use a stable request ID to prevent duplicate processing. Only the latest failed investigation can be retried.

Critical text symptoms trigger deterministic guidance immediately, without waiting for Gemini. Critical observations identified from media undergo a final rule check and can trigger the persistent stop-driving panel. Safety state remains escalated for that incident. The rules are conservative demonstrations, not a comprehensive automotive safety assessment; never treat absence of a rule trigger as permission to drive.

## Demo sensors: stable values and prepared history

1. Start a chat, expand **Demo sensors**, and check **Enable demo sensors**. Every chat starts with simulation off. The fictional defaults are four tire pressures at **2.3 bar**, **0 RPM**, and **22°C** coolant. These are demo values, separate from user-entered vehicle details; 2.3 bar is not an OEM specification.
2. Send: “I am safely parked. Investigate the current status of the fictional demo tire sensors.” Gemini can discover channels and read their current values. Open **Investigation activity** to inspect actual tool arguments and results.
3. Select **Rear-left tire**, choose **Slow pressure loss · 24 hours**, and click **Apply preset**. Its history instantly shows 2.3 → 1.8 bar; the other sensor values stay fixed. No message or Gemini request is triggered by an edit.
4. Send: “The demo tire warning is recurring and rear-left pressure seems to have gradually decreased. Investigate current readings and history, and explain what changed.” Gemini can call both current-value and history tools, select an appropriate window, and compare the trend. Responses and reports label sensor evidence simulated, with revision identifiers preserved in the activity results.
5. Use **Set value**, **Mark unavailable**, or **Custom trend** to alter one sensor. **Restore sensor** restores the selected channel and its flat baseline history; **Reset all** restores all six. A preset/custom trend replaces only the selected channel’s history. A numeric edit appends a step; it does not invent a gradual trend.

Prepared presets cover slow tire loss (24 hours), faster tire loss (one hour), coolant rise (22 → 110°C over ten minutes), RPM rise (0 → 1,800 over two minutes), and a healthy baseline. Custom trends accept starting/ending values and durations from **1 to 10,080 minutes** (seven days). Controls show a chart and expandable timestamped sample table.

There are no timers, background drift, or hardware connections. Readings and sample timestamps remain frozen until an explicit change; retrieval timestamps may change. History windows end at the frozen snapshot time. When no window is requested, each channel uses its scenario-specific duration; Gemini can request another duration up to seven days. Actual coverage is returned explicitly, with no invented samples before the prepared history. Unavailable current readings contain no number; historical readings from before the interruption remain available with a null marker for the interruption.

State is isolated per chat, survives browser reloads, and clears when the backend restarts. Use one backend worker. Mutations are locked while that chat has an active investigation, including direct API requests. Gemini has read-only sensor tools and cannot change the simulator. A trend supports an observation, not a confirmed cause or a roadworthiness judgment.

## Media and data handling

- Up to five attachments per message, 25 MB per file, 50 MB combined, and 10,000 text characters. Audio capture stops after two minutes and video after one minute; size limits also apply.
- Images are decoded and normalized to JPEG. Animated GIFs use the first frame. Audio is decoded to mono WAV and video to MP4 using the FFmpeg binary bundled with `imageio-ffmpeg`. Invalid or unsupported content produces an error rather than being ignored.
- Images are limited to 20 million decoded pixels to bound local processing memory.
- Actual media is uploaded through Gemini's Files API and submitted for model analysis. Processing is awaited; provider files are deleted in cleanup on success and failure. A cleanup failure is recorded in activity. Local originals remain available for playback until restart.
- Each new investigation rebuilds the canonical conversation context and reuploads prior attachments so follow-up questions can still refer to them after provider-file deletion. This increases processing and token costs for long media conversations.
- Microphone/camera access requires localhost or HTTPS and browser permission. Upload stays available if recording is denied or unsupported. Test your physical devices and browser codecs separately.
- Chats, reports, request IDs, jobs and original attachments live only in backend memory. Restarting clears them. This is a local single-user app; authentication, persistence, deployment and multiworker job coordination are not implemented.
- Uploaded media, prompts and search queries are sent to Google. Deleting Files API uploads does not delete stored Interactions history or change Google's service data policies. Model/tool continuations use stored interaction IDs within an investigation; subsequent chat turns are rebuilt from local state.

## API

| Method | Route | Behavior |
| --- | --- | --- |
| GET | `/api/health` | Configured provider/model, input capabilities and whether this process completed a real investigation; never returns credentials. |
| GET / POST | `/api/incidents` | List chats / create with optional `vehicle: {make, model, year}`. |
| GET | `/api/incidents/{id}` | Conversation, attachments, processing/error states, citations and execution events. |
| PATCH | `/api/incidents/{id}/vehicle` | Update user-confirmed make/model/year when no investigation is processing. |
| GET / PATCH | `/api/incidents/{id}/sensors` | Read simulator state / enable or disable with `{ "enabled": true }`. |
| PATCH | `/api/incidents/{id}/sensors/{sensor_name}` | Change one sensor: `kind` is `value`, `unavailable`, `preset`, `trend`, or `restore`. |
| POST | `/api/incidents/{id}/sensors/reset` | Restore all baseline values and histories, preserving the enable switch. |
| POST | `/api/incidents/{id}/messages` | Multipart `request_id`, optional `text`, repeated `files`; returns `202`. |
| POST | `/api/incidents/{id}/messages/{assistant_message_id}/retry` | Retry the latest failed assistant investigation; returns `202`. |
| GET | `/api/incidents/{id}/report` | Factual mechanic handoff with provenance and uncertainties. |
| GET | `/api/attachments/{id}` | Temporary original media for browser previews/playback. |
| GET | `/api/vehicles` | Empty list: no simulated or connected vehicle profiles in this phase. |

An investigation is bounded to six model turns, twelve custom tool invocations and 180 seconds, with a bounded cleanup grace period. Missing credentials, rejected model access, quota limits, blocked/empty replies and provider/tool errors are explicit; they do not produce fabricated success.

Browser writes are accepted only from the local frontend/API origins on ports 5173/8000; cross-origin websites cannot submit paid investigations through a browser form. This is not authentication or a public-hosting security boundary.

## Verification

```powershell
# Repository root: injected-provider unit/API tests, no live API charges
.venv/Scripts/python -m pytest backend/tests -q

# Opt-in LIVE checks: sends synthetic media and makes billable Gemini/Search calls
.venv/Scripts/python -m backend.tests.live_smoke

# Opt-in LIVE three-turn check: one follow-up at a time, narrowing to a leading cause
.venv/Scripts/python -m backend.tests.live_followup

# Opt-in LIVE sensor rehearsal: stable baseline, then gradual-loss tool investigation
.venv/Scripts/python -m backend.tests.live_sensors

# frontend: browser tests incur no provider charges; Vite AND FastAPI must be running
npm run build
npx playwright install chromium
npm run test:e2e
```

The live smoke test covers text, follow-up context, Google Search, custom tool execution and image/audio/video analysis using clearly synthetic media. The separate live sensor rehearsal verifies actual Gemini calls for stable readings and a gradual-loss history. Automated browser tests cover vehicle editing, polling, citations, activity, retries, recording/review/playback, mobile layout, denied permissions, preserved drafts, and the full simulator panel. Sensor browser tests use the real local simulator API; model-failure states use explicit HTTP fixtures and incur no provider charges.

## Done and deferred

Done: real Gemini, grounded search and URL context, multimodal inputs, bounded function execution, immediate safety escalation, vehicle editing, reports, asynchronous processing and retries, and optional per-chat demo sensors with current/history tools and presenter controls.

Deferred: hardware sensor connections, Bayesian rankings, offline Gemma, transcription services beyond Gemini's audio understanding, persistent storage, authentication and hosting. See [UI plan and mockups](UI/PLAN.md) and the broader [project specification](PROJECT_PLAN.md) for context.
