"""Round5 development-only empty-ASR fallback; no reference-based routing."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'evaluation/results/v020-hybrid'


def route(asr_text, baseline_text):
    return (asr_text, 'asr') if asr_text.strip() else (baseline_text, 'fallback')


def may_start(weekly_used_percent):
    # Unknown quota cannot authorize a new expensive package.
    return (isinstance(weekly_used_percent, (float, int))
            and not isinstance(weekly_used_percent, bool)
            and 0 <= weekly_used_percent <= 60)


def audit():
    source = ROOT / 'evaluation/results/v020-architecture/screen1/summary.json'
    data = json.loads(source.read_text())
    groups = {}
    details = []
    for d in data['details']:
        text, arm = route(d['candidate_text'], d['baseline_text'])
        m = d['candidate' if arm == 'asr' else 'baseline']
        g = groups.setdefault(d['group'], dict(n=0, fallback=0, baseline_correct=0,
            hybrid_correct=0, baseline_nonempty=0, hybrid_nonempty=0,
            baseline_errors=0, hybrid_errors=0, reference_words=0, repairs=[], losses=[]))
        g['n'] += 1
        g['fallback'] += arm == 'fallback'
        for label, score in [('baseline', d['baseline']), ('hybrid', m)]:
            g[label+'_correct'] += score['strict_match']
            g[label+'_nonempty'] += score['nonempty']
            g[label+'_errors'] += score['word_errors']
        g['reference_words'] += m['reference_words']
        if m['strict_match'] and not d['baseline']['strict_match']: g['repairs'].append(d['case_id'])
        if d['baseline']['strict_match'] and not m['strict_match']: g['losses'].append(d['case_id'])
        details.append(dict(case_id=d['case_id'], route=arm, text=text))
    OUT.mkdir(exist_ok=True)
    result = dict(kind='cached_development_replay', new_model_requests=0,
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        policy_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        groups=groups, details=details, independent_confirmation=False,
        chinese_measured=False, e2e_measured=False,
        warning='Route chosen after observing prior failures. No held-out evidence. Empty music also falls back; preserve hallucination.')
    with (OUT/'route_audit.json').open('x') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(groups, ensure_ascii=False, indent=2))


if __name__ == '__main__': audit()
