"""Score delivered English against bilingual SRT; lexical alignment is not word timing."""
import argparse
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from quality_audit import recover_format
from score_reference import words, ENTITIES


def milliseconds(value):
    h, m, s, ms = map(int, re.split('[:,]', value))
    return ((h * 60 + m) * 60 + s) * 1000 + ms


def read_srt(path):
    cues = []
    for block in re.split(r'\r?\n\s*\r?\n', Path(path).read_text(encoding='utf-8-sig').strip()):
        lines = block.splitlines()
        if len(lines) != 4:
            raise ValueError('Expected cue number, timing, English, Chinese')
        start, end = map(milliseconds, lines[1].split(' --> '))
        if end <= start or (cues and start < cues[-1]['end_ms']):
            raise ValueError('Invalid or overlapping SRT timing')
        cues.append(dict(id=int(lines[0]), start_ms=start, end_ms=end, english=lines[2], chinese=lines[3]))
    if [c['id'] for c in cues] != list(range(1, len(cues) + 1)):
        raise ValueError('Cue IDs must be consecutive')
    return cues


def align(reference, hypothesis):
    # Deterministic minimum-edit alignment. Reference cue membership survives
    # different model windows; no proportional allocation of words by duration.
    n, m = len(reference), len(hypothesis)
    dp = [list(range(m + 1))] + [[i] + [0] * m for i in range(1, n + 1)]
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            dp[i][j] = min(dp[i-1][j]+1, dp[i][j-1]+1,
                           dp[i-1][j-1]+(reference[i-1] != hypothesis[j-1]))
    operations = []
    i, j = n, m
    while i or j:
        if i and j and dp[i][j] == dp[i-1][j-1]+(reference[i-1] != hypothesis[j-1]):
            operations.append(('equal' if reference[i-1] == hypothesis[j-1] else 'substitute', i-1, j-1))
            i -= 1; j -= 1
        elif i and dp[i][j] == dp[i-1][j]+1:
            operations.append(('delete', i-1, None)); i -= 1
        else:
            operations.append(('insert', max(0, i-1), j-1)); j -= 1
    return list(reversed(operations))


def evaluate(cues, path, excluded):
    records = [json.loads(line) for line in Path(path).read_text().splitlines()]
    rows = [r for r in records if r.get('type') == 'window']
    if len({r['source'] for r in rows}) != 1 or len({r.get('pass', 1) for r in rows}) != 1:
        raise ValueError('Score exactly one source and one pass per file')
    if not any(r.get('type') == 'summary' for r in records):
        raise ValueError('Incomplete replay: no summary')
    ref, owners, hyp = [], [], []
    for cue in cues:
        tokens = words(cue['english']); ref.extend(tokens); owners.extend([cue['id']] * len(tokens))
    for row in rows:
        p = recover_format(row.get('raw', ''))
        if row.get('task') == 'english' and row.get('status') == 'transcription':
            hyp.extend(words(re.sub(r'^\s*(?:English|EN|Transcription)\s*[:：]', '', row['raw'], flags=re.I)))
        elif p.status == 'subtitle':
            hyp.extend(words(p.english))
    # Only exempt an exact declared omitted suffix, never arbitrary trailing text.
    omitted = words('almost in a form of')
    trim = next((k for k in range(len(omitted), 1, -1) if hyp[-k:] == omitted[:k]), 0)
    raw_ops = align(ref, hyp)
    scored_hyp = hyp[:-trim] if trim else hyp
    operations = align(ref, scored_hyp)
    counts, clean = Counter(), Counter()
    details = {c['id']: {**c, 'counts': Counter(), 'hypothesis_tokens': []} for c in cues}
    entity_total = entity_correct = 0
    for op, i, j in operations:
        cue_id = owners[i]
        counts[op] += 1
        details[cue_id]['counts'][op] += 1
        if j is not None:
            details[cue_id]['hypothesis_tokens'].append(scored_hyp[j])
        if cue_id not in excluded:
            clean[op] += 1
        if op != 'insert' and ref[i].removesuffix("'s") in ENTITIES:
            entity_total += 1; entity_correct += op == 'equal'
    def metric(counter, denominator):
        return {'reference_words': denominator, **dict(counter),
                'wer': sum(counter[k] for k in ['substitute', 'delete', 'insert']) / denominator if denominator else None}
    return {
        'file': str(path), 'reference_words': len(ref), 'hypothesis_words': len(hyp),
        'raw_full_wer': sum(op != 'equal' for op, _, _ in raw_ops) / len(ref),
        'ignored_exact_tail_tokens': trim,
        'full': metric(counts, len(ref)),
        'excluding_uncertain': metric(clean, sum(owner not in excluded for owner in owners)),
        'excluded_cue_ids': sorted(excluded),
        'aligned_entity_matches': entity_correct, 'reference_entity_mentions': entity_total,
        'aligned_entity_recall': entity_correct / entity_total if entity_total else None,
        'cue_review': list(details.values()),
        'caveat': 'Delivered-English WER includes parser omissions. Cue assignment uses lexical edit alignment, not forced audio alignment. Boundary insertions inherit previous reference cue. Chinese semantics and latency are not automatically graded.',
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference', type=Path)
    parser.add_argument('logs', nargs='+', type=Path)
    parser.add_argument('--exclude-cues', default='25')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    excluded = {int(v) for v in args.exclude_cues.split(',') if v}
    cues = read_srt(args.reference)
    if excluded - {c['id'] for c in cues}:
        parser.error('Unknown excluded cue')
    result = {'reference': str(args.reference), 'reference_sha256': hashlib.sha256(args.reference.read_bytes()).hexdigest(),
              'runs': [evaluate(cues, path, excluded) for path in args.logs]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    for run in result['runs']:
        print(json.dumps({k:v for k,v in run.items() if k != 'cue_review'}, ensure_ascii=False))
