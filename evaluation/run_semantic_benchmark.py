"""Opt-in local-model evaluation: same labelled cases and text as the typed verifier.

This measures author-labelled synthetic examples, not independently adjudicated
web accuracy. Does not fetch websites or send inputs to hosted model providers.
"""
import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services/intelligence'))
from claims import verify_claim
from llm import ModelGateway, selected_model
from semantic_evidence import review_records


async def main():
    cases = json.loads((ROOT / 'evaluation/fixtures/claim_adversarial.json').read_text())['cases']
    cases += [
        {'id': 'heading_location', 'entity': 'Delta Institute', 'field': {'name': 'location'}, 'value': 'Chennai',
         'text': '# Delta Institute\n\nLocation: Chennai\nResearch: Aerospace Engineering', 'expected': 'supported'},
        {'id': 'heading_specialization', 'entity': 'Delta Institute', 'field': {'name': 'specialization'}, 'value': 'Aerospace Engineering',
         'text': '# Delta Institute\n\nLocation: Chennai\nResearch specialization: Aerospace Engineering', 'expected': 'supported'},
        {'id': 'neighbor_heading', 'entity': 'Delta Institute', 'field': {'name': 'location'}, 'value': 'Chennai',
         'text': '# Delta Institute\n\nResearch: Aerospace Engineering\n\n# Beta University\n\nLocation: Chennai', 'expected': 'unknown'},
    ]
    model = ModelGateway()
    choice = {'provider': 'local', 'model': model.env.get('LOCAL_LLM_MODEL', 'qwen2.5:3b'), 'allow_external': False}
    token = selected_model.set(choice)
    rows = []
    started = time.monotonic()
    try:
        for case in cases:
            chunk = {'text': case['text'], 'url': 'https://benchmark.example/source', 'chunk_id': case['id'],
                     'http_status': 200, 'char_start': 0, 'content_sha256': hashlib.sha256(case['text'].encode()).hexdigest()}
            base = verify_claim(case['entity'], case['field'], case['value'], chunk)
            verdict = base['state']
            calls = 0
            if verdict == 'unknown':
                raw = {'canonical_name': case['entity'], case['field']['name']: case['value'], 'chunk_id': chunk['chunk_id']}
                reviews, _, calls = await review_records([raw], [chunk], {'fields': [case['field']]}, model.ainvoke)
                verdict = reviews.get(0, {}).get(case['field']['name'], {}).get('state', verdict)
            rows.append({'id': case['id'], 'expected': case['expected'], 'typed': base['state'], 'reviewed': verdict, 'model_calls': calls})
            print(case['id'], 'expected=' + case['expected'], 'reviewed=' + verdict, flush=True)
    finally:
        selected_model.reset(token)
    def metrics(method):
        return {'cases': len(rows), 'supported_correct': sum(r[method] == 'supported' and r['expected'] == 'supported' for r in rows),
                'false_support': sum(r[method] == 'supported' and r['expected'] != 'supported' for r in rows),
                'abstentions': sum(r[method] == 'unknown' for r in rows)}
    report = {'scope': 'Author-labelled synthetic cases; not a claim of live-web accuracy', 'model': choice['model'],
              'elapsed_seconds': round(time.monotonic() - started, 2), 'metrics': {m: metrics(m) for m in ['typed', 'reviewed']}, 'cases': rows}
    (ROOT / 'evaluation/results/semantic_benchmark.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report['metrics']), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
