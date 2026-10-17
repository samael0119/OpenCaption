"""Round5 bounded cached-ASR -> E2B text translation development screen."""
import gc
import hashlib
import json
from pathlib import Path
import sys
import time
import tomllib

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'evaluation/results/v020-hybrid'
STATE = OUT / 'state.json'
AUTO = Path('/home/hyh/.codex/automations/opencaption/automation.toml')
MODEL = Path('/home/hyh/Tools/litert/models/gemma-4-E2B-it.litertlm')
SYSTEM = 'Translate the provided English into simplified Chinese faithfully. Preserve names, numbers and negation. Output only the translation. Do not explain or add unstated facts.'


def read(p): return json.loads(p.read_text())


def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for c in iter(lambda: f.read(1048576), b''): h.update(c)
    return h.hexdigest()


def authorized(state, automation, quota, now):
    if state['status'] != 'active' or state['current_round'] != 5 or automation['status'] != 'ACTIVE':
        raise RuntimeError('Round5 inactive')
    if not 0 <= now-quota['observed_at_unix'] <= 120:
        raise RuntimeError('Quota snapshot stale/future')
    from v020_hybrid_route import may_start
    if quota.get('windowDurationMins') != 10080 or not may_start(quota.get('usedPercent')):
        raise RuntimeError('Weekly quota below40% or unknown')


def active():
    authorized(read(STATE), tomllib.loads(AUTO.read_text()), read(OUT/'quota.json'), time.time())


def resources():
    line = next(x for x in Path('/proc/self/cgroup').read_text().splitlines() if x.startswith('0::'))
    cg = Path('/sys/fs/cgroup')/line.split('::',1)[1].lstrip('/')
    d = {n:(cg/n).read_text().strip() for n in ['memory.max','memory.swap.max','memory.swap.current','memory.peak','memory.events']}
    if d['memory.max']=='max' or int(d['memory.max'])>6*1024**3 or d['memory.swap.max']!='0' or d['memory.swap.current']!='0':
        raise RuntimeError('Explicit <=6GiB/swap0 required')
    return d


def append(path, row):
    with path.open('a') as f: f.write(json.dumps(row,ensure_ascii=False)+'\n'); f.flush()


def prepare():
    active(); resources()
    summary = ROOT/'evaluation/results/v020-architecture/screen1/summary.json'
    prior = ROOT/'evaluation/results/v020-architecture/screen1/manifest.json'
    m = read(prior)
    baseline = m['baseline']
    cases = []
    for d in read(summary)['details']:
        if not d['candidate_text'].strip(): continue
        assert d['group'] in ['ordinary','natural_whisper']
        cases.append(dict(id=d['case_id'],group=d['group'],input_text=d['candidate_text'],
            reference_en=d['reference'],baseline=baseline[str(d['case_id'])]))
    assert len(cases)==30
    files = {}
    for name in ['evaluation/v020_hybrid_translate.py','evaluation/test_v020_hybrid_translate.py',
        'evaluation/v020_hybrid_route.py','evaluation/gemma_replay.py',
        'evaluation/protocol_candidate.py','evaluation/v020_architecture_screen.py',
        'scripts/run-v020-hybrid-translate']:
        files[name]=sha(ROOT/name)
    sdk = Path('/home/hyh/Tools/litert/litert-venv/lib/python3.12/site-packages/litert_lm')
    for p in sdk.rglob('*'):
        if p.is_file() and p.suffix!='.pyc': files[str(p)]=sha(p)
    files[str(summary.relative_to(ROOT))]=sha(summary)
    files[str(prior.relative_to(ROOT))]=sha(prior)
    frozen=dict(cases=cases,system=SYSTEM,files=files,model_sha256=sha(MODEL),
        config=dict(context=768,output=128,threads=4,top_k=1,temperature=0,thinking=False,speculation=None),
        batches=[list(range(n,n+10)) for n in range(0,30,10)],max_requests=30,retries=0,
        evaluation='AI-assisted faithful meaning vs fixed English reference; uncertain fails; not independent human gold. Preserve exact prior score for same case/raw/ref. Report three whisper losses separately.',
        scope='Cached known English -> Chinese development only; excludes live ASR/real display/switching. Six low-level cases remain original bilingual cache.')
    with (OUT/'translation_manifest.json').open('x') as f: json.dump(frozen,f,ensure_ascii=False,indent=2)


def verify():
    active(); m=read(OUT/'translation_manifest.json')
    assert m['system']==SYSTEM and m['max_requests']==30 and len(m['cases'])==30
    for p,v in m['files'].items():
        if sha(ROOT/p)!=v: raise RuntimeError('Frozen file changed: '+p)
    if sha(MODEL)!=m['model_sha256']: raise RuntimeError('Model changed')
    return m


def run(batch):
    m=verify(); limits=resources()
    if batch not in (0,1,2): raise RuntimeError('Batch out of bounds')
    path=OUT/f'translation_batch{batch}.jsonl'
    if path.exists(): raise RuntimeError('Already started, no implicit answer retries')
    for earlier in range(batch):
        rows=[json.loads(x) for x in (OUT/f'translation_batch{earlier}.jsonl').read_text().splitlines()]
        if rows[-1]['type']!='engine_closed' or not any(r['type']=='complete' for r in rows):
            raise RuntimeError('Prior batch incomplete')
    with path.open('x') as f: f.write(json.dumps(dict(type='metadata',manifest_sha256=sha(OUT/'translation_manifest.json'),resources=limits,quota=read(OUT/'quota.json')))+'\n')
    from gemma_replay import LiteRtRuntime,response_text
    from types import SimpleNamespace
    model=None
    try:
        t=time.monotonic()
        model=LiteRtRuntime(SimpleNamespace(model=MODEL,threads=4,max_new_tokens=128,hints='',task='bilingual',task_profile='baseline',system_profile='minimal',cache_mode='disk',speculative_decoding='default',max_context_tokens=768))
        append(path,dict(type='engine_initialized',load_ms=(time.monotonic()-t)*1000))
        api=model.api
        for index in m['batches'][batch]:
            active();case=m['cases'][index];append(path,dict(type='request_started',index=index,case_id=case['id']))
            t=time.monotonic()
            with model.engine.create_conversation(system_message=SYSTEM,thinking_config=api.ThinkingConfig(False,0),sampler_config=api.SamplerConfig(top_k=1,top_p=1.0,temperature=0.0),max_output_tokens=128) as conv:
                response=conv.send_message(api.Contents.of(case['input_text']),max_output_tokens=128,thinking_config=api.ThinkingConfig(False,0))
            append(path,dict(type='request',index=index,case_id=case['id'],input_text=case['input_text'],raw=response_text(response),inference_ms=(time.monotonic()-t)*1000))
        append(path,dict(type='complete',requests=10,resources=resources()))
    except BaseException as e:
        append(path,dict(type='failure',error=repr(e)));raise
    finally:
        if model is not None: model.close()
        gc.collect();append(path,dict(type='engine_closed'))


if __name__=='__main__':
    if sys.argv[1]=='prepare': prepare()
    elif sys.argv[1]=='verify': verify()
    elif sys.argv[1]=='run': run(int(sys.argv[2]))
