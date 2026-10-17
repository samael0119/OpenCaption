"""Frozen one-configuration E4B diagnostic, not a default-model migration."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import resource
import statistics
from types import SimpleNamespace

from v020_runtime_validation import ROOT, OUT, Protocol, infer, append
from gemma_replay import LiteRtRuntime
from v020_short_answer_validation import score
from score_reference import words, edit_distance


def summarize(manifest, results, protocol):
    baseline = {}
    for source in manifest['comparison_sources']:
        for line in (OUT/source).read_text().splitlines():
            row = json.loads(line)
            if row.get('type') == 'request' and row.get('task') == 'bilingual' and row.get('hints') == '':
                # Use the same current parser on cached E2B raw output.
                baseline[row['case_id']] = {**row, **protocol.parse('bilingual', row['raw'])}
    groups = {}
    for family in ['short', 'whisper', 'music']:
        cases = [c for c in manifest['cases'] if family ==
                 ('short' if 'label' in c else 'music' if c['kind'] == 'instrumental_music' else 'whisper')]
        group = {}
        for name, rows in [('cached_e2b', baseline), ('e4b', {r['case_id']: r for r in results})]:
            selected = [rows[c['id']] for c in cases]
            data = dict(n=len(cases), statuses=dict(Counter(r['status'] for r in selected)),
                        median_ms=statistics.median(r['inference_ms'] for r in selected))
            if family == 'short':
                scores = [score(r, c) for r,c in zip(selected,cases)]
                data.update(source_correct=sum(s['source_keyword_ok'] for s in scores),
                            joint_correct=sum(s['joint_keyword_ok'] for s in scores),
                            critical_no_six=[dict(id=c['id'],label=c['label'],status=r['status'],
                                english=r['english'],chinese=r['chinese'],**s)
                                for c,r,s in zip(cases,selected,scores) if c['label'] in ['no','six']])
            elif family == 'whisper':
                refs = [words(c['reference_en']) for c in cases]
                data.update(exact_command_correct=sum(words(r['english'])==ref for r,ref in zip(selected,refs)),
                    wer=sum(edit_distance(ref,words(r['english'])) for r,ref in zip(selected,refs))/sum(map(len,refs)))
            else:
                data['visible_hallucinations'] = sum(r['status']=='subtitle' for r in selected)
                data['outputs'] = [dict(id=r['case_id'],status=r['status'],raw=r['raw']) for r in selected]
            group[name] = data
        groups[family] = group
    (OUT/'e4b_diagnostic_summary.json').write_text(json.dumps(dict(groups=groups, scope=manifest['scope'],
        complete=True, requests=len(results), peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        independent_quality_acceptance=False, default_model_changed=False,
        comparison_limits='Separate cached E2B batch, not randomized runtime timing. Music E2B used older class snapshot; raw reparsed here.'),ensure_ascii=False,indent=2)+'\n')


def main():
    path = OUT/'e4b_diagnostic_manifest.json'
    manifest = json.loads(path.read_text())
    output = OUT/'e4b_diagnostic.jsonl'
    if output.exists():
        raise RuntimeError('Diagnostic already started: inspect checkpoint, no implicit retry')
    for file,digest in manifest['classes'].items():
        if hashlib.sha256(Path(file).read_bytes()).hexdigest()!=digest:
            raise RuntimeError('Frozen parser changed')
    for file,digest in manifest['comparison_sources'].items():
        if hashlib.sha256((OUT/file).read_bytes()).hexdigest()!=digest:
            raise RuntimeError('Cached comparison changed')
    for case in manifest['cases']:
        if hashlib.sha256((ROOT/case['path']).read_bytes()).hexdigest()!=case['sha256']:
            raise RuntimeError('Frozen audio changed')
    append(output,dict(type='metadata',utc=datetime.now(timezone.utc).isoformat(),
        manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),model_sha256=manifest['model_sha256'],
        config=dict(context=768,output=128,threads=4),scope=manifest['scope']))
    protocol=Protocol()
    model=None
    results=[]
    try:
        model=LiteRtRuntime(SimpleNamespace(model=Path(manifest['model']),threads=4,max_new_tokens=128,
            hints='',task='bilingual',task_profile='baseline',system_profile='minimal',cache_mode='disk',
            speculative_decoding='default',max_context_tokens=768))
        for case in manifest['cases']:
            row=infer(model,protocol,case,'bilingual','')
            append(output,dict(type='request',**row));results.append(row)
        append(output,dict(type='complete',requests=len(results),utc=datetime.now(timezone.utc).isoformat()))
        model.close();model=None
        summarize(manifest,results,protocol)
    finally:
        if model is not None:
            model.close()
        protocol.close()


if __name__=='__main__':
    main()
