#!/usr/bin/env python3
"""Read-only, offline EDUCATIONAL demonstration. No vehicle access or ECU writes."""
import argparse, json
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
rows=[json.loads(x) for x in (BASE/'data/synthetic_demo_scenarios.jsonl').read_text(encoding='utf-8').splitlines() if x.strip()]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--list',action='store_true')
p.add_argument('--scenario',default='DEMO-02')
a=p.parse_args()
if a.list:
    for r in rows:print(r['id'], '-',r['scenario'])
else:
    r=next((r for r in rows if r['id']==a.scenario),None)
    if not r:p.error('Unknown scenario. Try --list')
    print('=== SIMULATED DATA -- NOT FROM A REAL BMW ===')
    print('Scenario:',r['scenario'])
    print('Driver:',r['user_report'])
    print('Signals:',json.dumps(r['telemetry'],indent=2))
    print('Evidence limitations:',r['disclaimer'])
    print('Possible next read-only tools:', ', '.join(r['next_tools']))
    print('Safe triage:',r['safe_response'])
    print('Source IDs:',', '.join(r['sources']))
