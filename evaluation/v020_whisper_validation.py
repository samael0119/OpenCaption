"""Natural whisper holdout: original published prompts, no Chinese gold claim."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evaluation/results/v020-independent'


def main():
    output=OUT/'whisper_model.jsonl'
    if output.exists():
        raise RuntimeError('Existing whisper batch; inspect before retry')
    from v020_short_answer_validation import compiled_snapshot
    classes=compiled_snapshot()
    manifest=json.loads((OUT/'whisper_holdout_cases.json').read_text())
    cases=manifest['cases']
    for case in cases:
        assert hashlib.sha256((ROOT/case['path']).read_bytes()).hexdigest()==case['sha256']
    from v020_runtime_validation import Protocol,runtime,infer,append
    from score_reference import words,edit_distance
    append(output,dict(type='metadata',utc=datetime.now(timezone.utc).isoformat(),classes=classes,
        context=768,output_tokens=128,threads=4,case_manifest_sha256=hashlib.sha256((OUT/'whisper_holdout_cases.json').read_bytes()).hexdigest(),
        scope=manifest['reference_scope']))
    protocol=Protocol();model=runtime();results=[]
    try:
        for index,case in enumerate(cases):
            for hints in (['','CS2 broadcast.'] if index%2==0 else ['CS2 broadcast.','']):
                row=infer(model,protocol,case,'bilingual',hints)
                results.append(row);append(output,dict(type='request',**row))
        for case in cases:
            row=infer(model,protocol,case,'english','CS2 broadcast.')
            results.append(row);append(output,dict(type='request',**row))
        append(output,dict(type='complete',requests=len(results),utc=datetime.now(timezone.utc).isoformat()))
    finally:
        model.close();protocol.close()
    by_id={c['id']:c for c in cases};groups={}
    for task,hints in sorted({(r['task'],r['hints']) for r in results}):
        selected=[r for r in results if r['task']==task and r['hints']==hints]
        refs=[words(by_id[r['case_id']]['reference_en']) for r in selected]
        total=sum(map(len,refs))
        groups[task+'|'+hints]=dict(n=len(selected),statuses=dict(Counter(r['status'] for r in selected)),
            reference_words=total,wer=sum(edit_distance(ref,words(r['english'])) for r,ref in zip(selected,refs))/total,
            exact_command_correct=sum(words(r['english'])==ref for r,ref in zip(selected,refs)),
            median_inference_ms=statistics.median(r['inference_ms'] for r in selected))
    (OUT/'whisper_model_summary.json').write_text(json.dumps(dict(groups=groups,requests=len(results),
        scope=manifest['reference_scope']),ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(groups,ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
