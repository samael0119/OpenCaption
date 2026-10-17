"""Candidate2: FP32 encoder only; immutable candidate1 remains the control."""
import gc
import hashlib
import json
import os
from pathlib import Path
import statistics
import sys
import time
import tomllib
import wave

from score_reference import words, edit_distance

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / 'evaluation/results/v020-architecture'
OUT = BASE / 'screen2'
STATE = BASE / 'state.json'
AUTO = Path('/home/hyh/.codex/automations/opencaption/automation.toml')
CYCLE = 'architecture-20261015'
CONFIG = dict(num_threads=4, sample_rate=16000, feature_dim=80, provider='cpu',
              decoding_method='greedy_search', enable_endpoint_detection=False,
              hotwords_file='', lm='', blank_penalty=0.0)


def read(path): return json.loads(path.read_text())


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''): h.update(chunk)
    return h.hexdigest()


def write_new(path, value):
    with path.open('x') as f: json.dump(value, f, ensure_ascii=False, indent=2)


def append(value):
    with (OUT / 'requests.jsonl').open('a') as f:
        f.write(json.dumps(value, ensure_ascii=False) + '\n')
        f.flush()


def authorize(state, automation):
    if state.get('cycle_id') != CYCLE or state.get('status') != 'active' or automation.get('status') != 'ACTIVE':
        raise RuntimeError('Architecture cycle not authorized/active')
    if state.get('consecutive_complete_rounds_without_gain', 0) >= 3:
        raise RuntimeError('Complete-round stop reached')


def active(): authorize(read(STATE), tomllib.loads(AUTO.read_text()))


def resources():
    line = next(l for l in Path('/proc/self/cgroup').read_text().splitlines() if l.startswith('0::'))
    cg = Path('/sys/fs/cgroup') / line.split('::', 1)[1].lstrip('/')
    values = {n: (cg/n).read_text().strip() for n in
              ['memory.max', 'memory.high', 'memory.swap.max', 'memory.swap.current', 'memory.peak', 'memory.events']}
    if values['memory.max'] == 'max' or int(values['memory.max']) > 6*1024**3:
        raise RuntimeError('Missing bounded cgroup')
    if values['memory.swap.max'] != '0' or values['memory.swap.current'] != '0':
        raise RuntimeError('Swap must be zero')
    return values


def metrics(reference, text):
    ref, got = words(reference), words(text)
    return dict(strict_match=bool(ref) and ref == got, nonempty=bool(text.strip()),
                word_errors=edit_distance(ref, got), reference_words=len(ref))


def chunks(samples, size=2560):
    for offset in range(0, len(samples), size): yield offset, samples[offset:offset+size]



def replace_encoder(model, replacement):
    if model['revision'] != replacement['revision']:
        raise RuntimeError('Precision comparison requires same model revision')
    original = [r for r in model['files'] if Path(r['path']).name.startswith('encoder-')]
    if len(original) != 1 or not original[0]['path'].endswith('chunk-16-left-128.int8.onnx'):
        raise RuntimeError('Expected frozen int8 encoder')
    if not replacement['path'].endswith('encoder-epoch-99-avg-1-chunk-16-left-128.onnx'):
        raise RuntimeError('Wrong encoder topology')
    result = dict(model)
    result['files'] = [dict(replacement) if r is original[0] else dict(r) for r in model['files']]
    return result


def prepare():
    active(); resources(); OUT.mkdir(exist_ok=True)
    if (OUT/'manifest.json').exists() or (OUT/'requests.jsonl').exists():
        raise RuntimeError('Already prepared/started')
    prior = ROOT/'evaluation/results/v020-round3/candidate1'
    old = read(prior/'manifest.json')
    rows = [json.loads(l) for l in (prior/'requests.jsonl').read_text().splitlines()]
    assert rows[-1]['type'] == 'complete'
    baseline = {str(r['case_id']): r for r in rows if r.get('type') == 'request' and r['mode'] == 'auto'}
    cases = old['cases']; assert len(cases) == len(baseline) == 41
    for c in cases:
        assert digest(ROOT/c['path']) == c['sha256'] == baseline[str(c['id'])]['input_sha256']
    model = replace_encoder(read(BASE/'model_files.json'), read(BASE/'precision_encoder.json'))
    files = {r['path']: r['sha256'] for r in model['files']}
    numpy_deps=ROOT/'evaluation/results/s0-20261013/deps'
    sys.path.insert(0,str(numpy_deps));sys.path.insert(0,str(BASE/'deps'))
    import numpy as np
    import sherpa_onnx
    assert np.__version__=='2.2.6' and sherpa_onnx.__version__=='1.13.8'
    for folder in [BASE/'deps',*numpy_deps.glob('numpy*')]:
        for p in folder.rglob('*'):
            if p.is_file() and p.suffix != '.pyc': files[str(p.relative_to(ROOT))] = digest(p)
    for name in ['evaluation/v020_architecture_precision.py', 'evaluation/test_v020_architecture_precision.py',
                 'evaluation/v020_architecture_screen.py', 'evaluation/test_v020_architecture_screen.py',
                 'evaluation/score_reference.py', 'scripts/run-v020-architecture-screen',
                 'scripts/run-v020-architecture-precision',
                 'evaluation/results/v020-architecture/screen1/manifest.json',
                 'evaluation/results/v020-architecture/screen1/requests.jsonl',
                 'evaluation/results/v020-architecture/precision_encoder.json',
                 'evaluation/results/v020-architecture/pip_install_report.json']:
        files[name] = digest(ROOT/name)
    write_new(OUT/'manifest.json', dict(cycle_id=CYCLE, files=files, model=model,
        baseline_path=str((prior/'requests.jsonl').relative_to(ROOT)), baseline_sha256=digest(prior/'requests.jsonl'),
        cases=cases, baseline=baseline, config=CONFIG, max_requests=41, max_engine_loads=1,
        tail_flush_samples=10560, stream_feed_samples=2560, answer_retries=0,
        scope='Observed regression source-word screen. Cached E2B is not fresh latency or independent confirmation.',
        gate='target source errors -20% and net repairs>=3; no whisper strict/coverage regression or new critical errors; preserve all music outputs; Chinese and display still unmeasured'))
    verify()


def verify():
    active(); m = read(OUT/'manifest.json')
    if m['config'] != CONFIG or m['max_requests'] != 41 or len(m['cases']) != 41:
        raise RuntimeError('Configuration/budget changed')
    for path, sha in m['files'].items():
        if digest(ROOT/path) != sha: raise RuntimeError('Frozen dependency changed: '+path)
    if digest(ROOT/m['baseline_path']) != m['baseline_sha256']: raise RuntimeError('Cache changed')
    for c in m['cases']:
        if digest(ROOT/c['path']) != c['sha256']: raise RuntimeError('PCM changed')
    return m


def run():
    if (OUT/'requests.jsonl').exists(): raise RuntimeError('Already started; never implicitly retry')
    m=verify(); limits=resources()
    with (OUT/'requests.jsonl').open('x') as f:
        f.write(json.dumps(dict(type='metadata', manifest_sha256=digest(OUT/'manifest.json'), resources=limits))+'\n')
    sys.path.insert(0, str(ROOT/'evaluation/results/s0-20261013/deps'))
    sys.path.insert(0, str(BASE/'deps'))
    import numpy as np
    import sherpa_onnx
    assert sherpa_onnx.__version__ == '1.13.8'
    paths={Path(r['path']).name: str(ROOT/r['path']) for r in m['model']['files']}
    kwargs = dict(CONFIG)
    for part in ['encoder','decoder','joiner']:
        suffix='' if part=='encoder' else '.int8'
        kwargs[part]=paths[f'{part}-epoch-99-avg-1-chunk-16-left-128{suffix}.onnx']
    kwargs['tokens']=paths['tokens.txt']
    state=read(STATE)
    if state['candidate_attempts']['zipformer_streaming'] != 1: raise RuntimeError('Candidate2 requires exactly one prior attempt')
    state['candidate_attempts']['zipformer_streaming']=2
    state['next_package']='A0_screen2_in_progress'
    temporary=STATE.with_suffix('.tmp'); temporary.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n'); os.replace(temporary,STATE)
    append(dict(type='engine_initializing', requested_config=kwargs))
    start=time.monotonic(); recognizer=sherpa_onnx.OnlineRecognizer.from_transducer(**kwargs)
    append(dict(type='engine_initialized', initialization_ms=(time.monotonic()-start)*1000))
    for index,case in enumerate(m['cases']):
        active(); append(dict(type='request_started',index=index,case_id=case['id']))
        with wave.open(str(ROOT/case['path']),'rb') as wav:
            assert wav.getnchannels()==1 and wav.getframerate()==16000 and wav.getsampwidth()==2
            samples=np.frombuffer(wav.readframes(wav.getnframes()),dtype='<i2').astype(np.float32)/32768.0
        start=time.monotonic(); stream=recognizer.create_stream(); history=[]; previous=''
        for offset,chunk in chunks(samples,m['stream_feed_samples']):
            stream.accept_waveform(16000,chunk)
            while recognizer.is_ready(stream): recognizer.decode_stream(stream)
            current=recognizer.get_result(stream)
            if current!=previous:
                history.append(dict(source_position_ms=(offset+len(chunk))/16,text=current,
                                    compute_elapsed_ms=(time.monotonic()-start)*1000))
                previous=current
        before_flush=recognizer.get_result(stream)
        stream.accept_waveform(16000,np.zeros(m['tail_flush_samples'],dtype=np.float32))
        stream.input_finished()
        while recognizer.is_ready(stream): recognizer.decode_stream(stream)
        text=recognizer.get_result(stream)
        append(dict(type='request',index=index,case_id=case['id'],group=case['group'],raw_text=text,
                    text_before_flush=before_flush,partial_history=history,input_sha256=case['sha256'],
                    samples=len(samples),tail_flush_ms=660,source_only_compute_ms=(time.monotonic()-start)*1000,
                    **metrics(case.get('reference_en',''),text)))
        del stream
    del recognizer; gc.collect(); append(dict(type='engine_closed'))
    append(dict(type='complete',requests=41,resources=resources()))


def summarize():
    m=verify(); rows=[json.loads(l) for l in (OUT/'requests.jsonl').read_text().splitlines()]
    assert rows[-1]['type']=='complete'
    req=[r for r in rows if r['type']=='request'];starts=[r for r in rows if r['type']=='request_started']
    assert len(req)==len(starts)==41 and [r['case_id'] for r in req]==[c['id'] for c in m['cases']]
    details=[]
    for c,r in zip(m['cases'],req):
        b=m['baseline'][str(c['id'])]
        details.append(dict(case_id=c['id'],group=c['group'],reference=c.get('reference_en',''),
            baseline_text=b['english'],candidate_text=r['raw_text'],
            baseline=metrics(c.get('reference_en',''),b['english']),candidate=metrics(c.get('reference_en',''),r['raw_text']),
            candidate_compute_ms=r['source_only_compute_ms']))
    groups={}
    for group in sorted({d['group'] for d in details}):
        ds=[d for d in details if d['group']==group];g=dict(n=len(ds))
        for arm in ['baseline','candidate']:
            n=sum(d[arm]['reference_words'] for d in ds);e=sum(d[arm]['word_errors'] for d in ds)
            g[arm]=dict(strict_correct=sum(d[arm]['strict_match'] for d in ds),nonempty=sum(d[arm]['nonempty'] for d in ds),
                        word_errors=e,reference_words=n,wer=e/n if n else None)
        g['strict_repairs']=[d['case_id'] for d in ds if not d['baseline']['strict_match'] and d['candidate']['strict_match']]
        g['strict_losses']=[d['case_id'] for d in ds if d['baseline']['strict_match'] and not d['candidate']['strict_match']]
        g['source_compute_median_ms']=statistics.median(d['candidate_compute_ms'] for d in ds)
        groups[group]=g
    result=dict(complete=True,new_asr_requests=41,baseline_cached_rows=41,groups=groups,details=details,
                resources=rows[-1]['resources'],real_display_latency=False,independent_acceptance=False,
                interpretation='Source-only screen; all texts retained. ASR timing excludes translation/loading/UI;660ms tail is explicit. Known data, no population CI.')
    write_new(OUT/'summary.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='details'},ensure_ascii=False,indent=2))


if __name__=='__main__':
    {'prepare':prepare,'run':run,'summarize':summarize}[sys.argv[1]]()
