"""Quantify the frozen development screen; semantic judgments remain explicit."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import statistics

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'evaluation/results/accuracy-style-20261019'
ARMS = ['standard', 'natural', 'meaning_natural']


def words(text):
    return re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text.lower())


def distance(reference, hypothesis):
    previous = list(range(len(hypothesis) + 1))
    for i, a in enumerate(reference, 1):
        current = [i]
        for j, b in enumerate(hypothesis, 1):
            current.append(min(previous[j] + 1, current[j-1] + 1, previous[j-1] + (a != b)))
        previous = current
    return previous[-1]


def main():
    manifest = json.loads((OUT / 'manifest.json').read_text())
    events = [json.loads(line) for line in (OUT / 'requests.jsonl').read_text().splitlines()]
    rows = [r for r in events if r['type'] == 'request']
    assert len(rows) == 96 and len({r['index'] for r in rows}) == 96
    assert len([r for r in events if r['type'] == 'started']) == 96
    assert any(r['type'] == 'complete' for r in events)
    assert any(r['type'] == 'closed' for r in events)
    for row, expected in zip(rows, manifest['order']):
        assert all(row[k] == expected[k] for k in ['index', 'case_id', 'arm', 'modality'])
    audio = {(r['case_id'], r['arm']): r for r in rows if r['modality'] == 'audio'}
    cases = manifest['cases']
    primary = [c for c in cases if c['primary'] and c['reference_en']]
    speech = [c for c in cases if c['reference_en']]
    music = [c for c in cases if not c['reference_en']]
    summary = dict(actual_requests=96, audio_requests=72, text_requests=24,
                   derived_community=12, prior_zero_request_engineering_attempts=1,
                   speech_cases=len(speech), primary_cases=len(primary), music_cases=len(music), arms={})
    review_path = OUT / 'semantic_review.json'
    review = json.loads(review_path.read_text()) if review_path.exists() else None
    for arm in ARMS:
        group = [audio[(c['id'], arm)] for c in cases]
        scored = [audio[(c['id'], arm)] for c in primary]
        errors = sum(distance(words(c['reference_en']), words(audio[(c['id'], arm)]['english'])) for c in speech)
        nwords = sum(len(words(c['reference_en'])) for c in speech)
        result = dict(statuses=dict(Counter(r['status'] for r in group)),
                      speech_delivered=sum(audio[(c['id'], arm)]['status'] == 'subtitle' for c in speech),
                      music_visible_hallucinations=sum(audio[(c['id'], arm)]['status'] == 'subtitle' for c in music),
                      wer_literal=dict(errors=errors, words=nwords, rate=errors/nwords),
                      service_p50_ms=statistics.median(r['inference_ms'] for r in group),
                      all_service_ms=[round(r['inference_ms'], 2) for r in group])
        if review:
            ratings = [review['audio'][c['id']][arm] for c in primary]
            for c, rating in zip(primary, ratings):
                assert len(rating['units']) == len(c['semantic_units']), c['id']
            result['semantic_units_preserved'] = sum(sum(x['units']) for x in ratings)
            result['semantic_units_total'] = sum(len(x['units']) for x in ratings)
            result['whole_sentences'] = sum(x['whole'] for x in ratings)
            result['critical_errors'] = sum(x['critical'] for x in ratings)
            result['critical_error_cases'] = [c['id'] for c, rating in zip(primary, ratings) if rating['critical']]
        summary['arms'][arm] = result
    if review:
        for arm in ARMS[1:]:
            pairs = [(review['audio'][c['id']]['standard'], review['audio'][c['id']][arm], c['id']) for c in primary]
            summary['arms'][arm]['whole_repairs'] = [i for a, b, i in pairs if not a['whole'] and b['whole']]
            summary['arms'][arm]['whole_losses'] = [i for a, b, i in pairs if a['whole'] and not b['whole']]
            summary['arms'][arm]['new_critical_cases'] = [i for a, b, i in pairs if not a['critical'] and b['critical']]
            summary['arms'][arm]['new_critical_types'] = {i: sorted(set(b['critical_types']) - set(a['critical_types']))
                for a, b, i in pairs if set(b['critical_types']) - set(a['critical_types'])}
            summary['arms'][arm]['unit_repairs'] = sum(sum(not x and y for x, y in zip(a['units'], b['units'])) for a, b, _ in pairs)
            summary['arms'][arm]['unit_losses'] = sum(sum(x and not y for x, y in zip(a['units'], b['units'])) for a, b, _ in pairs)
        summary['text_review'] = review['text_summary']
    summary['scope'] = 'Known development and synthetic text, AI-assisted semantic judgments; no independent human quality/preference, no Android E2E.'
    summary['resource_final'] = [r['resources'] for r in events if r['type'] == 'closed'][-1]
    summary['load_ms'] = [r['load_ms'] for r in events if r['type'] == 'loaded']
    summary['raw_sha256'] = hashlib.sha256((OUT / 'requests.jsonl').read_bytes()).hexdigest()
    summary['review_sha256'] = hashlib.sha256(review_path.read_bytes()).hexdigest() if review else None
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
