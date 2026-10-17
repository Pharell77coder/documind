"""Tiny deterministic retrieval smoke evaluation; no LLM quality claim."""
import json
import tempfile
from pathlib import Path
from ingestion import extract
from providers import DemoEmbedder
from store import Store

ROOT=Path(__file__).parent
CASES=[
 ('Quelle est la conservation des sauvegardes PostgreSQL ?', 'guide-projet.txt'),
 ('Quand le déploiement du projet Orion est-il prévu ?', 'guide-projet.txt'),
 ('Pourquoi un PDF scanné nécessite-t-il un OCR ?', 'formation-rag.md'),
 ('Comment évaluer la pertinence des passages et la fidélité des réponses ?', 'formation-rag.md'),
 ('Quel est le salaire du directeur ?', None),
 ('astronomie galaxies telescopes', None),
]

def evaluate():
    rows=[]
    with tempfile.TemporaryDirectory() as tmp:
        store=Store(tmp,DemoEmbedder())
        try:
            for p in sorted((ROOT/'examples').iterdir()):
                name,doc_id,chunks=extract(p.name,p.read_bytes());store.ingest(name,doc_id,chunks)
            for question,expected in CASES:
                sources=store.search(question,4,0.20)
                top=sources[0]['filename'] if sources else None
                rows.append(dict(question=question,expected=expected,top1=top,passed=top==expected))
        finally: store.close()
    report=dict(mode='demo lexical hashing, no LLM',threshold=0.20,cases=len(rows),passed=sum(r['passed'] for r in rows),results=rows,
        limitation='Six hand-written cases on two synthetic documents. This is a smoke check, not a measure of general retrieval or answer faithfulness.')
    (ROOT/'evaluation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':evaluate()
