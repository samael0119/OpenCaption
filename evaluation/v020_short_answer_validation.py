"""Run frozen human keyword labels after the updated Kotlin parser is built.

This checks literal short answers; it is not CS2/Chinese sentence gold, and
the translated single-word equivalents were declared before inference.
"""
from collections import Counter
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'evaluation/results/v020-independent'
NUMBERS = dict(zip(['zero','one','two','three','four','five','six','seven','eight','nine'], map(str, range(10))))


def normalized(value):
    return re.sub(r'[^a-z0-9\u3400-\u9fff]', '', value.lower())


def score(row, case):
    english = normalized(row.get('english', ''))
    chinese = normalized(row.get('chinese', ''))
    valid = row.get('status') == 'subtitle'
    english_options = {case['label'], NUMBERS.get(case['label'], case['label'])}
    source_ok = valid and english in english_options
    translation_ok = (None if row['task']=='english' else
                      valid and chinese in case['reference_zh_options'])
    return dict(protocol_ok=valid, source_keyword_ok=source_ok,
                translation_keyword_ok=translation_ok,
                joint_keyword_ok=source_ok and (translation_ok is not False))


def compiled_snapshot():
    directory = ROOT/'build/app/tmp/kotlin-classes/gemmaE2EDebug/dev/opencaption/opencaption'
    main_class = directory/'E2eProtocol.class'
    names_class = directory/'E2ePreservedNames.class'
    prior = json.loads((OUT/'protocol_class_snapshot.json').read_text())['classes']
    previous = prior[str(main_class.relative_to(ROOT))]
    current = hashlib.sha256(main_class.read_bytes()).hexdigest()
    if current == previous or not names_class.exists():
        raise RuntimeError('New numeric/name parser has not been built. Wait for long runs, then test/build first.')
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [*directory.glob('E2eProtocol*.class'), names_class]}


def request_plan(cases):
    plan = []
    for index, case in enumerate(cases):
        for hints in (['','CS2 broadcast.'] if index%2==0 else ['CS2 broadcast.','']):
            plan.append((case['id'], 'bilingual', hints))
    for task in ['english', 'auto_zh']:
        plan.extend((case['id'], task, 'CS2 broadcast.') for case in cases)
    return plan


def resume_prefix(rows, classes, manifest_digest, plan):
    if not rows or rows[0].get('type') != 'metadata':
        raise RuntimeError('Missing original batch metadata')
    meta = rows[0]
    if (meta.get('classes') != classes or meta.get('case_manifest_sha256') != manifest_digest
            or (meta.get('context'), meta.get('output_tokens'), meta.get('threads')) != (768,128,4)):
        raise RuntimeError('Frozen parser, manifest or model configuration changed')
    results = []
    for row in rows[1:]:
        if row.get('type') == 'resume':
            if row.get('already_recorded') != len(results):
                raise RuntimeError('Invalid resume boundary')
            continue
        if row.get('type') != 'request':
            raise RuntimeError('Complete/unknown batch record; inspect rather than rerun')
        key = (row.get('case_id'),row.get('task'),row.get('hints'))
        if len(results) >= len(plan) or key != plan[len(results)]:
            raise RuntimeError('Duplicate, reordered or missing frozen request')
        results.append(row)
    if len(results) >= len(plan):
        raise RuntimeError('All requests already recorded; only summarize, do not infer again')
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    # No heavy runtime imports until the build guard and frozen manifest pass.
    classes = compiled_snapshot()
    output = OUT/'short_answers.jsonl'
    if output.exists() and not args.resume:
        raise RuntimeError('Already started; inspect checkpoint before any retry')
    manifest = json.loads((OUT/'short_answer_cases.json').read_text())
    cases = manifest['cases']
    plan = request_plan(cases)
    manifest_digest = hashlib.sha256((OUT/'short_answer_cases.json').read_bytes()).hexdigest()
    for case in cases:
        assert hashlib.sha256((ROOT/case['path']).read_bytes()).hexdigest() == case['sha256']
    results = []
    if args.resume:
        rows = [json.loads(x) for x in output.read_text().splitlines()]
        results = resume_prefix(rows, classes, manifest_digest, plan)
    from v020_runtime_validation import runtime, Protocol, infer, append
    if args.resume:
        append(output,dict(type='resume',utc=datetime.now(timezone.utc).isoformat(),already_recorded=len(results),
            reason='Local bridge framing lost empty Chinese column on the first English request',
            unrecorded_inflight_request=list(plan[len(results)]),model_reloaded=True))
    else:
        append(output, dict(type='metadata', utc=datetime.now(timezone.utc).isoformat(), classes=classes,
                            case_manifest_sha256=manifest_digest, context=768, output_tokens=128, threads=4,
                            scope=manifest['reference_scope']))
    protocol = Protocol()
    model = runtime()
    by_id = {case['id']:case for case in cases}
    try:
        for case_id, task, hints in plan[len(results):]:
            case = by_id[case_id]
            row = infer(model, protocol, case, task, hints)
            row.update(score(row, case)); results.append(row)
            append(output, dict(type='request', **row))
        append(output, dict(type='complete', requests=len(results), utc=datetime.now(timezone.utc).isoformat()))
    finally:
        model.close(); protocol.close()
    groups = {}
    for task, hints in sorted({(r['task'],r['hints']) for r in results}):
        selected = [r for r in results if r['task']==task and r['hints']==hints]
        groups[task+'|'+hints] = dict(n=len(selected), statuses=dict(Counter(r['status'] for r in selected)),
            source_correct=sum(r['source_keyword_ok'] for r in selected),
            joint_correct=sum(r['joint_keyword_ok'] for r in selected),
            translation_correct=None if task=='english' else sum(r['translation_keyword_ok'] for r in selected))
    (OUT/'short_answers_summary.json').write_text(json.dumps(dict(groups=groups, requests=len(results), resumed=args.resume,
        scope=manifest['reference_scope']), ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(groups, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
