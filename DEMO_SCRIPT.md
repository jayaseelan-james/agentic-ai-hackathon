# AutoSage — two-minute demo

**Focus:** one sensor-driven investigation, BMW-specific evidence, restricted web access with hosted Gemma, and a safety escalation.

## Before recording

- Open `/simulator` and `/bmw` side by side. Use a fresh BMW chat.
- Keep the computer connected: remote breakdown mode blocks application web tools while permitting the Gemini API connection. Do not disable Wi-Fi for this demonstration.
- Select **Tire pressure loss**. It sets the rear-left reading to **1.8 bar**, with a recorded decline from **2.3 bar over 24 hours**. These are simulated values and a configured reference, not BMW pressure specifications.
- Start in standard mode. Rehearse both standard and restricted investigations with your account before recording. Confirm that the restricted response actually completes with `gemma-4-26b-a4b-it`; a mode badge alone proves configuration, not successful model execution.
- Leave the investigation details collapsed initially. Keep a fresh General chat ready for the brake example.
- Use actual recorded results. If generation exceeds the timing below, cut only the waiting time and mark it “Processing time shortened.” Do not present the sample chat prompts below as actual assistant replies.

## What to showcase and narration

Read the quoted narration word for word. The timings include short pauses and clicks.

| Time | Screen and action | Narration transcript |
| --- | --- | --- |
| **0:00–0:15** | Show the BMW chat, then the simulator beside it. | “When a warning appears, drivers need a useful next step. AutoSage combines a conversation with vehicle readings and reference material. This demo uses a shared simulated vehicle, with a dedicated BMW 330i workspace.” |
| **0:15–0:35** | In the simulator, select **Tire pressure loss**. Point to the rear-left reading and its history chart. | “Here, the rear-left tire reads one point eight bar. Its recorded history falls from two point three over twenty-four hours. These are simulated observations, not BMW pressure specifications. Every investigation freezes its readings, so later edits cannot rewrite the evidence.” |
| **0:35–0:55** | In the BMW chat, click **Check what’s wrong with my car**. Show processing, then the actual answer. | “I can start an investigation with one click. AutoSage reads the available channels and their history before asking the model to explain what needs attention. Missing measurements stay unknown, and the answer includes a safe next action.” |
| **0:55–1:15** | Expand **Investigation details**. Show real sensor events and any returned BMW reference. Show probability charts only if this run produced them. | “The details panel shows which tools actually ran. BMW mode can retrieve bundled reference material and explain model-specific limitations. A reading is evidence, not proof of a failed part. Any displayed probabilities come from a synthetic demonstration model, not validated diagnostic confidence.” |
| **1:15–1:40** | Enable **Block internet access (remote breakdown)**. Start a new BMW chat and run the automatic check again. Show the completed Gemma response and its activity. | “Now I simulate a remote breakdown. Web search and external-page retrieval are blocked, and new investigations use Gemma four, twenty-six B, strictly. It still runs through the Gemini API; this is restricted connectivity, not fully offline inference. Sensors and bundled references remain available.” |
| **1:40–2:00** | In a fresh General chat, submit the brake prompt below. Show the immediate persistent stop-driving panel. | “Finally, a safety-critical symptom triggers immediate guidance without waiting for a language model. The driver is told not to continue driving and to seek professional assistance. AutoSage helps organize evidence and next steps; it does not certify that a car is safe to drive.” |

## Exact chat prompts

**Automatic sensor review:** click **Check what’s wrong with my car**. No typed prompt is required.

**Optional BMW reference follow-up, if your first result did not retrieve a reference:**

> Use the bundled BMW G20 tire-pressure reference to explain what this reading can and cannot tell us. Do not look up a website.

**Safety example, in a fresh chat:**

> My brake pedal is soft and the brakes are not stopping the car properly.

## What to verify in the actual replies

- The tire answer should use the returned **1.8-bar** reading and the recorded trend if relevant, without treating **2.3 bar** as a universal BMW specification or claiming a confirmed puncture.
- The restricted run must finish successfully with **Gemma 4 26B**. Its request must have no Google Search or URL-context tools. The UI should attribute the reply to Gemma and indicate blocked web access.
- Only point to a BMW reference, probability chart, or tool event if it is present in your actual run. Prior web citations do not establish a new live lookup in restricted mode.
- The brake example should immediately display persistent stop-driving guidance and recommend professional assistance. Do not demonstrate a driving test or a brake repair.

**If the hosted Gemma call fails:** show the explicit failure and describe it honestly. The toggle and model selection have been checked against the running local backend, but account access and a successful live Gemma response must be rehearsed separately before the recording.
