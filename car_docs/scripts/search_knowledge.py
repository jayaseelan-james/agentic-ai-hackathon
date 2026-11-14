#!/usr/bin/env python3
"""Search local original RAG cards without network or external libraries."""
from pathlib import Path
import json,sys
base=Path(__file__).resolve().parents[1]
query=' '.join(sys.argv[1:]).casefold().strip()
if not query:
    print('Usage: python scripts/search_knowledge.py cooling')
    raise SystemExit(2)
cards=[json.loads(s) for s in (base/'data/rag_knowledge_cards.jsonl').read_text(encoding='utf-8').splitlines() if s.strip()]
hits=[(sum((t in (r['title']+' '+r['content']+' '+r['domain']).casefold()) for t in query.split()),r) for r in cards]
for score,r in sorted(hits, key=lambda x:x[0],reverse=True):
    if score:
        print('\n',r['id'],'|',r['title'],'| sources:',','.join(r['source_ids']))
        print(' ',r['content'])
