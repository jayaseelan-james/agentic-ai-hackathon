#!/usr/bin/env python3
"""Convert this pack's own original Markdown notes into simple local JSONL chunks."""
from pathlib import Path
import json,re
base=Path(__file__).resolve().parents[1]
out=base/'data'/'note_chunks_generated.jsonl'
with out.open('w',encoding='utf-8') as f:
    for p in sorted((base/'notes').glob('*.md')):
        content=p.read_text(encoding='utf-8').strip()
        blocks=re.split(r'\n(?=##? )',content)
        for i,block in enumerate(blocks):
            if not block.strip():continue
            row={'id':f'{p.stem}-{i:02d}','source_path':f'notes/{p.name}','kind':'original_summary', 'text':block.strip(),'vehicle':'BMW G20 330i petrol', 'retrieval_safety':'confirm VIN applicability'}
            f.write(json.dumps(row,ensure_ascii=False)+'\n')
print('Generated',out)
