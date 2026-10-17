"""No-model three-way audit for the final bounded precision candidate."""
import json
from pathlib import Path
import statistics

from v020_architecture_screen import ROOT, BASE, digest


def load_run(name):
    out=BASE/name;manifest=json.loads((out/'manifest.json').read_text())
    for path,sha in manifest['files'].items():
        if digest(ROOT/path)!=sha: raise RuntimeError('Frozen file changed: '+path)
    if digest(ROOT/manifest['baseline_path'])!=manifest['baseline_sha256']:
        raise RuntimeError('Baseline cache changed')
    for case in manifest['cases']:
        if digest(ROOT/case['path'])!=case['sha256']: raise RuntimeError('PCM changed')
    rows=[json.loads(l) for l in (out/'requests.jsonl').read_text().splitlines()]
    if rows[-1]['type']!='complete' or rows[-1]['requests']!=41: raise RuntimeError('Not complete')
    starts=[r for r in rows if r['type']=='request_started']
    requests=[r for r in rows if r['type']=='request']
    for items in [starts,requests]:
        if len(items)!=41 or [r['index'] for r in items]!=list(range(41)):
            raise RuntimeError('Request count/order mismatch')
        if [r['case_id'] for r in items]!=[c['id'] for c in manifest['cases']]:
            raise RuntimeError('Case order mismatch')
    if [r['type'] for r in rows if r['type'].startswith('engine_')] != ['engine_initializing','engine_initialized','engine_closed']:
        raise RuntimeError('Lifetime mismatch')
    limits=rows[-1]['resources'];events=dict(l.split() for l in limits['memory.events'].splitlines())
    if limits['memory.swap.current']!='0' or limits['memory.swap.max']!='0' or int(limits['memory.max'])>2*1024**3:
        raise RuntimeError('Resource limit violated')
    if int(events['oom']) or int(events['oom_kill']): raise RuntimeError('OOM')
    return manifest,requests,limits


def main():
    target=BASE/'screen2/three_way_audit.json'
    if target.exists(): raise RuntimeError('Audit already saved')
    a,ar,al=load_run('screen1');b,br,bl=load_run('screen2')
    for field in ['cases','baseline_sha256','config','max_requests','tail_flush_samples','stream_feed_samples','answer_retries']:
        if a[field]!=b[field]: raise RuntimeError('Unexpected variable changed: '+field)
    if a['model']['revision']!=b['model']['revision']: raise RuntimeError('Model revision changed')
    retained_a=[r for r in a['model']['files'] if not Path(r['path']).name.startswith('encoder-')]
    retained_b=[r for r in b['model']['files'] if not Path(r['path']).name.startswith('encoder-')]
    if retained_a!=retained_b: raise RuntimeError('Non-encoder model changed')
    groups={}
    for group in sorted({r['group'] for r in ar}):
        pairs=[(x,y) for x,y in zip(ar,br) if x['group']==group]
        groups[group]=dict(n=len(pairs),identical_raw=sum(x['raw_text']==y['raw_text'] for x,y in pairs),
            int8_nonempty=sum(x['nonempty'] for x,y in pairs),fp32_nonempty=sum(y['nonempty'] for x,y in pairs),
            strict_repairs=[x['case_id'] for x,y in pairs if not x['strict_match'] and y['strict_match']],
            strict_losses=[x['case_id'] for x,y in pairs if x['strict_match'] and not y['strict_match']],
            int8_compute_median_ms=statistics.median(x['source_only_compute_ms'] for x,y in pairs),
            fp32_compute_median_ms=statistics.median(y['source_only_compute_ms'] for x,y in pairs))
    result=dict(complete=True,actual_new_requests_this_package=41,actual_cycle_requests=82,
        cached_E2B_rows=41,cached_int8_rows=41,only_model_change='same-revision encoder int8 toFP32;decoder/joiner/tokens unchanged',
        groups=groups,identical_raw_pairs=sum(x['raw_text']==y['raw_text'] for x,y in zip(ar,br)),
        changed_raw=[dict(id=x['case_id'],group=x['group'],int8=x['raw_text'],fp32=y['raw_text']) for x,y in zip(ar,br) if x['raw_text']!=y['raw_text']],
        int8_resources=al,fp32_resources=bl,
        requests_sha256={'int8':digest(BASE/'screen1/requests.jsonl'),'fp32':digest(BASE/'screen2/requests.jsonl')},
        chinese_quality_measured=False,real_E2E_measured=False,independent_acceptance=False,
        timing_note='Separate runs on known data; int8 replay has no fresh timing. Descriptive costs only; includes computation of660msflush but no wall-clock audio playback,translation,model switching or UI.')
    target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__': main()
