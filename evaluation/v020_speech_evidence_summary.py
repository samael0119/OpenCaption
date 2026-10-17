"""One frozen diagnostic rule, full trace integrity, never a product pass."""
import json
import math
from pathlib import Path

OUT = Path(__file__).parent/'results/v020-independent'


def candidate(row, rule):
    if not all(isinstance(row.get(k), (int,float)) and math.isfinite(row[k])
               for k in ['samples','rms','max_vad']):
        return False
    return (0 <= row['max_vad'] < rule['max_vad_exclusive'] and
            row['samples'] >= rule['min_samples'] and row['rms'] >= rule['min_rms'])


def summarize(lines, plan):
    expected = {(mode,c['id']):c['label'] for mode in ['reset','continuous'] for c in plan['cases']}
    rows, seen, errors = [], set(), []
    complete = bool(lines) and lines[-1] == '#complete\t'+str(len(expected))
    for line in lines:
        if line.startswith('#'):
            continue
        fields = line.split('\t')
        if len(fields) != 9:
            errors.append('invalid_row'); continue
        mode, identifier, label, samples, rms, peak, mean, above, elapsed = fields
        key = (mode, identifier)
        if key in seen or key not in expected or expected.get(key) != label:
            errors.append('case_missing_duplicate_or_label_mismatch')
        seen.add(key)
        row = dict(mode=mode, case_id=identifier, label=label, samples=int(samples),
                   rms=float(rms), max_vad=float(peak), mean_vad=float(mean),
                   calls_above_half=int(above), elapsed_ms=float(elapsed))
        if (not all(math.isfinite(row[k]) for k in ['rms','max_vad','mean_vad','elapsed_ms']) or
            not 0 < row['samples'] <= 80000 or not 0 <= row['rms'] <= 1 or
            not 0 <= row['max_vad'] <= 1 or not 0 <= row['mean_vad'] <= 1 or
            not 0 <= row['calls_above_half'] <= math.ceil(row['samples']/320) or row['elapsed_ms'] < 0):
            errors.append('invalid_stats')
        row['candidate_veto'] = candidate(row, plan['rule'])
        rows.append(row)
    integrity = complete and seen == set(expected) and not errors
    groups = {}
    for mode in ['reset','continuous']:
        selected = [r for r in rows if r['mode']==mode]
        groups[mode] = dict(speech_cases=sum(r['label']=='speech' for r in selected),
            false_veto_known_speech=sum(r['label']=='speech' and r['candidate_veto'] for r in selected),
            music_cases=sum(r['label']=='music' for r in selected),
            music_candidate_veto=sum(r['label']=='music' and r['candidate_veto'] for r in selected),
            short_or_quiet_kept=sum(r['samples']<plan['rule']['min_samples'] or r['rms']<plan['rule']['min_rms'] for r in selected))
    return dict(integrity_pass=integrity, issues=errors, complete_marker=complete, groups=groups,
                rows=rows, product_music_acceptance=False, scope=plan['scope'])


def main():
    plan = json.loads((OUT/'speech_evidence_plan.json').read_text())
    result = summarize((OUT/'speech_evidence.tsv').read_text().splitlines(),plan)
    (OUT/'speech_evidence_summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='rows'},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
