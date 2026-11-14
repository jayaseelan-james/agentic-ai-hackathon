# AutoSage — Gemini Diagnostic Chat

React + TypeScript + Vite + Tailwind UI with a FastAPI backend and real Gemini investigations. Supports text, images, microphone recordings, camera video and gallery uploads, with grounded references and a separate operator inspector.

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

1. Start a chat; the assistant asks for missing make/model/year in a follow-up when needed. No vehicle-details form is required. The default is “Vehicle details not provided.” A model-specific specification requires confirmed vehicle details and relevant documentation.
2. Submit text and/or media. FastAPI returns `202` with the saved user message, immediate safety status, and a processing assistant message. The UI polls the incident for the result.
3. Gemini can use built-in Google Search and URL context, plus validated `record_observations`, `classify_diagnosis`, `get_vehicle_profile`, `update_vehicle_profile`, `create_mechanic_report`, `list_available_sensors`, `read_vehicle_sensors`, and `read_sensor_history` functions. The operator inspector shows real actions, arguments and returned data, not hidden reasoning. Sources are mapped from returned annotations; Google Search suggestions appear in a sandboxed frame.
4. The chat asks one targeted follow-up question at a time, using each answer and relevant tool evidence to narrow the problem. It avoids listing possible causes upfront. When the evidence supports a leading explanation, it connects that explanation to the observations and gives a safe next action; unresolved uncertainty is referred for inspection rather than forced into a definitive diagnosis. Model claims remain unconfirmed. A report can be copied when the agent creates a mechanic handoff.
5. A failed investigation exposes a retry button that reuses the saved message and attachments. Network-submission retries use a stable request ID to prevent duplicate processing. Only the latest failed investigation can be retried.

Critical text symptoms trigger deterministic guidance immediately, without waiting for Gemini. Critical observations identified from media undergo a final rule check and can trigger the persistent stop-driving panel. Safety state remains escalated for that incident. The rules are conservative demonstrations, not a comprehensive automotive safety assessment; never treat absence of a rule trigger as permission to drive.

## Bayesian-guided conversations

Tire, brake, cooling, starting/charging and engine-running investigations use a small locally trained naive Bayes model. Chat asks one useful question at a time rather than listing competing causes. The backend selects questions by expected information gain (above 0.01 bits), prioritizes conflicting reports, and stops when no useful unanswered question remains, you decline/stop, or critical safety escalation applies. An inconclusive result stays inconclusive; a leading category is unconfirmed and never certifies roadworthiness.

Supported categories are tire pressure loss / TPMS monitoring issue / other, and brake hydraulic concern / indicator issue / other. Inputs are explicit English reports of yellow TPMS warnings, low pressure, soft pedals, and persistent red brake warnings, plus validated simulated tire readings. Short yes/no answers apply only to the pending question. Ambiguous, hypothetical, and unconfirmed media observations stay unknown. No exact failed parts are inferred.

**Synthetic training only:** the checked-in model was fitted from 10,000 generated examples per domain with Laplace smoothing; 2,000 separately generated examples per domain provide a synthetic consistency check. The generator follows the toy probabilities in `PROJECT_PLAN.md` §6.2. This is not automotive training data, calibrated confidence, or evidence of real diagnostic accuracy. Missing observations are marginalized; repeated evidence is counted once. Other/unmodeled leaders, top probability below 0.60, margin below 0.15, or unresolved conflicts yield inconclusive results.

Reproduce training explicitly, without internet or API calls:

```powershell
.venv/Scripts/python -m backend.train_bayes
```

This writes the training/validation JSONL datasets and `backend/data/bayes_model.json`, with counts, seeds, dataset SHA-256 hashes and generator/model versions. Training never runs during conversations. Inference reads only the saved fitted parameters. Missing or invalid artifacts produce `model_error` without fabricated probabilities.

Try: **“My yellow TPMS warning is showing.”** Answer the single question from an observation you already have, or say **“I don't know.”** No driving test or mechanical procedure is needed. Use **“Stop asking questions”** to end questioning. Full rankings, evidence and model version are available in the operator **Investigation inspector**. General conversations outside this workflow still use Gemini normally.

For the sensor demo, explicitly identify the **fictional demo vehicle** and confirm it was **parked with cold tires**. Only then may current tool readings use the local synthetic handbook's fictional 2.3-bar reference. An enabled simulator alone never associates readings with your real car. Any valid low wheel supports a low-pressure observation; establishing no low wheels requires all four readings. Missing reference/conditions, unavailable readings and stale revisions are not filled in. Sensor edits invalidate current conclusions; historical messages retain their original results.

The backend ensures classification runs even if Gemini omits it and identifies backend versus model tool execution in activity. Critical brake guidance bypasses Gemini and never waits for probabilities. If Gemini fails or is not configured, locally computed results remain available alongside an explicit provider error/retry; this is not a successful Gemini or Gemma response. State remains in memory and clears on backend restart.

## Demo sensors: stable values and prepared history

Open **http://127.0.0.1:5173/simulator** in a separate tab. The customer chat remains at `/`. Enable shared simulation or select one of five prepared scenarios. Every chat uses the same global numeric vehicle state for its next investigation.

The simulator exposes **17 channels across tires, brakes, cooling, starting/charging and engine running**. Edit inline numbers, mark channels unavailable, restore individual baselines, apply compatible presets, or set a custom trend (1–10,080 minutes). Charts and timestamped tables preserve gaps. Reset restores all baselines; all 17 channels start with editable illustrative values for a parked vehicle with its engine off; these are fictional demo defaults, not verified healthy readings. Scenario values are fictional, not manufacturer specifications.

Every accepted investigation freezes the simulator revision. Edits can continue while a response is running; they affect the next accepted message, not running jobs or historical evidence. Retries retain their original snapshot. State survives browser reloads and clears on backend restart; use one backend worker. There is no hardware connection or background drift.

The operator page polls shared readings. Edits use `If-Match`; stale writes return 409 and require an explicit reload. Unsaved drafts remain visible. The investigation inspector shows evidence, media processing, provider/model, synthetic Bayesian rankings, tool arguments/results and per-message revisions. These details are hidden from customer chat.

Gemini receives actual text, images, audio and video, source-linked observation registration, the five-domain Bayesian classifier, enabled simulator current/history tools, Google Search and URL context. Media evidence must reference a processed attachment owned by the incident; ambiguous observations stay unknown. Numeric trends do not establish hidden faults. Web references never become incident measurements. Synthetic model posteriors are not real-world confidence.

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

Global simulator API: `GET/PATCH /api/simulator`, `PATCH /api/simulator/sensors/{name}`, `POST /api/simulator/scenario` and `POST /api/simulator/reset`. All global writes require an `If-Match` revision. Legacy incident sensor routes are compatibility aliases to shared state. `GET /api/incidents/{id}/inspection` provides the operator evidence and execution view.

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

Bayesian tests additionally verify deterministic dataset hashes, fitted-parameter inference, unknown/conflicting/duplicate evidence, real/demo context, frozen revisions, media provenance, provider failures and persistent safety. Browser checks cover the customer UI and shared simulator across tabs, including stale draft rejection and camera playback before attaching clips.

## Done and deferred

Done: shared simulator, separated operator/customer pages, source-linked multimodal evidence, real Gemini, grounded search and URL context, multimodal inputs, bounded function execution, immediate safety escalation, vehicle editing, reports, asynchronous processing and retries, and optional global demo sensors with current/history tools and presenter controls.

Done additionally: reproducible synthetic Bayesian training, evidence-aware local tire/brake ranking, one-question dialogue selection, and operator-only model/provenance details.

Deferred: hardware sensor connections, full local manual search, offline Gemma, transcription services beyond Gemini's audio understanding, persistent storage, authentication and hosting. See [UI plan and mockups](UI/PLAN.md) and the broader [project specification](PROJECT_PLAN.md) for context.


### Approved synthetic domain expansion

The v2 model contains 18 categories across five independent domains. In addition to tire and brake:

| Domain | Categories | Observations |
|---|---|---|
| Cooling | Coolant loss; circulation problem; fan/control issue; other/unmodeled | High-temperature warning; coolant loss; overheating while stationary |
| Starting and charging | Low battery charge; starter circuit issue; charging system issue; other/unmodeled | Slow cranking; clicking without cranking; battery warning while running |
| Engine running | Ignition/misfire concern; air/fuel delivery concern; sensor/control concern; other/unmodeled | Rough idle; hesitation; check-engine warning |

Each domain has 10,000 training and 2,000 separate validation examples. The new probabilities in `backend/train_bayes.py` are hand-authored synthetic assumptions, not automotive statistics. Runtime uses `autosage-trained-v2`; reproduce with `python -m backend.train_bayes`. New-domain evidence initially comes from explicit English user reports, not invented sensor measurements. Unknowns, conflicts, provenance and one-question information-gain selection remain shared. High-temperature and stationary-overheating reports stop questioning and escalate, including short answers to pending questions. Synthetic validation does not establish real diagnostic accuracy.

Customer answers use natural vehicle-reading terminology during the controlled demo; simulator provenance remains explicit on the operator page. The agent answers truthfully if asked about hardware and cannot certify roadworthiness.

### Chat activity and probability charts

Chat displays the actual agent/backend execution timeline as processing is polled. Each used Bayesian domain has a horizontal probability chart when a finite distribution is returned. Domains without results show an unavailable state. Sensor channels actually read are grouped by domain with current values and returned history; there is no independent per-channel fault probability in the current model. Percentages describe synthetic-trained model estimates, not validated diagnostic confidence. Raw tool arguments and full provenance remain in the operator inspector.

The chat keeps investigation extras inside one collapsed dropdown. Its header shows the animated current event during processing. Completion collapses the panel; expanding reveals high-level Bayesian probability charts first, followed by the full event history. Channel details remain in the operator inspector. Reduced-motion preferences disable the spinner animation.
