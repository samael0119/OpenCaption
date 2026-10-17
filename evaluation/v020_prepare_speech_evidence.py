"""Freeze case order and one conservative diagnostic rule before VAD results."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'evaluation/results/v020-independent'


def main():
    target = OUT/'speech_evidence_plan.json'
    if target.exists():
        raise RuntimeError('Already frozen. Do not adjust the rule to fit outcomes.')
    cases = []
    for name in ['frozen_cases.json', 'short_answer_cases.json']:
        manifest = json.loads((OUT/name).read_text())
        for case in manifest['cases']:
            assert hashlib.sha256((ROOT/case['path']).read_bytes()).hexdigest() == case['sha256']
            cases.append(dict(id=case['id'], path=case['path'],
                              label='music' if case['kind']=='instrumental_music' else 'speech',
                              kind=case['kind']))
    tsv = OUT/'speech_evidence_cases.tsv'
    tsv.write_text(''.join(f"{c['id']}\t{c['label']}\t{c['path']}\n" for c in cases))
    plan = dict(cases=cases, order='original frozen 28 then frozen short 24; same order for reset/continuous',
                rule=dict(min_samples=32000, min_rms=.02, max_vad_exclusive=.01),
                scope='Diagnostic candidate only, no product veto enabled. Short/quiet cases kept; low-energy audio is never discarded. Missing/invalid VAD data keeps audio. Reset evidence cannot prove continuous-capture safety; weak speech under loud backgrounds remains unverified.',
                cases_tsv_sha256=hashlib.sha256(tsv.read_bytes()).hexdigest())
    target.write_text(json.dumps(plan, ensure_ascii=False, indent=2)+'\n')
    print(f'Frozen {len(cases)} cases; diagnostic rule is not a shipped speech filter.')


if __name__ == '__main__':
    main()
