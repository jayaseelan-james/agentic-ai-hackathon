# BMW 330i (G20) Offline Diagnostic Research Pack

**Built:** 14 November 2026 · **Target:** 2019–2024 G20 330i petrol · **Use:** educational AI vehicle diagnostics / hackathon.

## What is actually offline

This ZIP includes original, authored research notes, **32 verified online-source references**, an evidence-annotated sensor catalogue (17 channels including four individual tire pressures), a JSONL RAG corpus (22 cards), six synthetic demo fault scenarios, a brief 2021 US recall metadata table (7 campaigns), an agent-context prompt, local search HTML, and optional scripts. **No BMW repair-manual or third-party manual page was downloaded or reprinted in full.**

BMW's technical-training PDF explicitly restricts copying and transferring without permission. BMW AOS/ISTA and third-party manual sites are not assumed redistributable, even when publicly accessible. See `LEGAL_AND_PROVENANCE.md`.

## Open offline first

- `START_HERE.html` — visual local browser for the included notes/cards (runs with no internet).
- `AGENT_CONTEXT.md` — copy into Gemini or use as system context for your diagnostic agent.
- `notes/` — domain-specific technical research and safety policies.
- `data/sensor_catalog.json` — what may exist vs what generic OBD can actually read.
- `data/rag_knowledge_cards.jsonl` — pre-chunked original cards with source IDs.
- `data/synthetic_demo_scenarios.jsonl` — sample flows for your hackathon; **not real sensor data**.
- `data/us_2021_330i_recalls_verified.csv` — US NHTSA 2021 330i observed 7 campaigns, **not VIN-confirmed**.
- `sources/source_catalog.csv` — click-through references for the copyrighted primary manuals.

## Minimal local demo

No dependencies:

```bash
python scripts/demo_diagnostic.py --list
python scripts/demo_diagnostic.py --scenario DEMO-04
python scripts/search_knowledge.py coolant
```

To run a **read-only** OBD test on a car you own/are authorized to test, you must independently install a compatible adapter, the required library and verify vehicle compatibility. The example script deliberately does **not** write to ECUs, reset fault codes or control actuators.

## Obtaining full manuals lawfully

1. Consult the official BMW Driver's Guide for your VIN; it supports offline use within the official app.
2. Obtain an authorized BMW AOS subscription or licensed repair access for current technical repair instructions.
3. Add documents you have permission to process to a local folder and ingest their own text into your private RAG corpus (observe license terms). No bulk download of copyrighted manuals is included.

## Limitations

This is **not an exhaustive offline copy of all BMW G20 documents or all 2019–2024 recalls**. More than ten thousand repair items are catalogued by a third party and cannot be reproduced here. Network-based original document retrieval was not available for inclusion; source references have been checked from live public indexes. All notes are educational hypotheses, not BMW service procedures. Exact vehicle and VIN determine applicability.
