"""Last gain candidate: extreme-low-level eligibility, cached identical inputs.

46 new calls for synthetic low-level counterexamples; old gold stays unchanged.
One same-model run, exact-zero/frame preservation, no speech veto or retries.
"""
import array
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import wave

import v020_fleurs_pilot as pilot
from v020_coupling_candidate import require_active
from v020_gain_candidate import boost

ROOT = pilot.ROOT
OUT = ROOT / 'evaluation/results/v020-convergence'
STATE = OUT / 'optimization_state.json'
MANIFEST = OUT / 'gain2_manifest.json'
OUTPUT = OUT / 'gain2_requests.jsonl'
THRESHOLD = 256


def restricted(samples):
    peak = max((abs(v) for v in samples), default=0)
    return boost(samples) if 0 < peak < THRESHOLD else (array.array('h', samples), 1.0)


def pcm(path):
    with wave.open(str(path)) as wav:
        if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1,2,16000):
            raise RuntimeError('Unexpected PCM format')
        return array.array('h', wav.readframes(wav.getnframes()))


def save(path, samples):
    with wave.open(str(path), 'wb') as wav:
        wav.setparams((1,2,16000,len(samples),'NONE','not compressed'))
        wav.writeframes(samples.tobytes())


def peak200(samples):
    peak = max(map(abs, samples))
    if peak == 0:
        raise RuntimeError('Expected nonzero counterexample')
    return array.array('h',(round(v*200/peak) for v in samples))


def prepare():
    require_active()
    if MANIFEST.exists() or OUTPUT.exists():
        raise RuntimeError('Already frozen/started')
    if sys.byteorder!='little':raise RuntimeError('Requires little-endian PCM')
    old=pilot.read(OUT/'gain1_manifest.json')
    old_rows=[json.loads(l) for l in (OUT/'gain1_requests.jsonl').read_text().splitlines()]
    if old_rows[-1]['type']!='complete':raise RuntimeError('Prior run incomplete')
    rows={(x['case_id'],x['mode']):x for x in old_rows if x['type'] in ['request','unchanged_reuse']}
    if len(rows)!=80:raise RuntimeError('Prior pairs incomplete')
    files={**old['dependencies'],**old['references'],
        'evaluation/results/v020-convergence/gain1_manifest.json':pilot.digest(OUT/'gain1_manifest.json'),
        'evaluation/results/v020-convergence/gain1_requests.jsonl':pilot.digest(OUT/'gain1_requests.jsonl'),
        'evaluation/results/v020-convergence/gain1_semantic_review.json':pilot.digest(OUT/'gain1_semantic_review.json'),
        'evaluation/results/v020-independent/joint_live_run1_music_audit.json':pilot.digest(pilot.OUT/'joint_live_run1_music_audit.json'),
        'evaluation/results/v020-independent/joint_live_run1_model.jsonl':pilot.digest(pilot.OUT/'joint_live_run1_model.jsonl')}
    directory=OUT/'gain2_audio';directory.mkdir()
    cached=[];fresh=[]
    for c in old['cases']:
        source=pcm(ROOT/c['path'])
        if pilot.digest(ROOT/c['path'])!=c['sha256']:raise RuntimeError('Source changed')
        transformed,gain=restricted(source)
        target=directory/(str(c['id'])+'-restricted.wav');save(target,transformed)
        cache_mode='gain' if gain>1 else 'baseline'
        old_audio=c['gain_path'] if cache_mode=='gain' else c['path']
        if pcm(ROOT/old_audio)!=transformed:raise RuntimeError('Cached input not identical')
        for mode,cache in [('baseline',rows[(c['id'],'baseline')]),('gain2',rows[(c['id'],cache_mode)])]:
            cached.append(dict(case_id=c['id'],group=c['group'],mode=mode,cache_mode=cache_mode if mode=='gain2' else 'baseline',
                original_path=c['path'],input_path=c['path'] if mode=='baseline' else str(target.relative_to(ROOT)),
                input_sha256=pilot.digest(ROOT/c['path']) if mode=='baseline' else pilot.digest(target),
                gain=gain if mode=='gain2' else 1.0,
                original_reference=c,actual_cached_result=cache,
                note='Identical PCM/model/prompt; reuse is strategy replay, not a new inference or independent validation. Historical decoder time is not candidate2 measured latency.'))
        if c['group'] in ['natural_whisper','music']:
            fresh.append(dict(c,id='quiet-'+str(c['id']),group='synthetic_attenuated_whisper' if c['group']=='natural_whisper' else 'quiet_music',
                              source_path=c['path'],prepared_samples=peak200(source)))
    audit=pilot.read(pilot.OUT/'joint_live_run1_music_audit.json')
    fail=next(x for x in audit['rows'] if x['window']==148)
    if [(x['kind'],x['end_sample']-x['start_sample']) for x in fail['parts']] != [('added_zero',11648),('known_instrumental_music',10432)]:
        raise RuntimeError('Known short failure coordinates changed')
    music=pcm(ROOT/fail['parts'][1]['path'])[:10432]
    source=array.array('h',[0]*11648)+music
    # Actual E2B prepareShort: prefix zeros to2s, retaining every source sample.
    encoded=array.array('h',[0]*(32000-len(source)))+source
    if len(encoded)!=32000 or encoded[-len(source):]!=source:raise RuntimeError('Short-input shape invalid')
    short_path=directory/'known-short-window148.wav';save(short_path,encoded)
    candidate,gain=restricted(encoded)
    if candidate!=encoded or gain!=1:raise RuntimeError('Known short input unexpectedly eligible')
    for mode in ['baseline','gain2']:
        cached.append(dict(case_id='known-short-window148',group='known_short_music',mode=mode,
            input_path=str(short_path.relative_to(ROOT)),input_sha256=pilot.digest(short_path),gain=1,
            actual_cached_result=fail,note='Historical full product model result from window148. Source partitions and prepareShort reconstructed; retained hallucination, not a new measured request.'))
    fresh.append(dict(id='quiet-known-short-window148',group='quiet_music',kind='instrumental_music',
        reference_en='',reference_zh='',source_path=str(short_path.relative_to(ROOT)),
        prepared_samples=peak200(encoded),expect_no_speech=True))
    for i,c in enumerate(fresh):
        source=c.pop('prepared_samples');transformed,gain=restricted(source)
        if max(map(abs,source))!=200 or gain!=16:raise RuntimeError('Counterexample level changed')
        baseline=directory/(str(c['id'])+'-baseline.wav');candidate=directory/(str(c['id'])+'-gain2.wav')
        save(baseline,source);save(candidate,transformed)
        c.update(path=str(baseline.relative_to(ROOT)),sha256=pilot.digest(baseline),gain_path=str(candidate.relative_to(ROOT)),
                 gain_sha256=pilot.digest(candidate),samples=len(source),gain_factor=gain,
                 source_sha256=pilot.digest(ROOT/c['source_path']),mode_order=['baseline','gain2'] if i%2==0 else ['gain2','baseline'])
    if len(cached)!=82 or len(fresh)!=23:raise RuntimeError('Fixed material count changed')
    for name in ['evaluation/v020_gain_candidate2.py','scripts/run-v020-gain-candidate2','evaluation/test_v020_gain_candidate2.py']:
        files[name]=pilot.digest(ROOT/name)
    m=dict(frozen_at=datetime.now().astimezone().isoformat(),files=files,model_sha256=old['model_sha256'],config=old['config'],
        cached=cached,fresh=fresh,threshold_pcm_peak=THRESHOLD,
        policy='Only0<peak<256 uses max16 gain; all other samples unchanged, zero remains zero. Condition development-derived, not a speech veto or proven safe policy.',
        bounds=dict(max_new_requests=46,retries=0,timeout_seconds=600,memory_max_bytes=6*1024**3,swap_max=0),
        primary='Same original6case/18semantic rubric via explicitly cached exact input replay. Require>=3 repaired Chinese units and>=20% fewer lost units; uncertainty not correct.',
        guards='Original whisper/ordinary unchanged; synthetic attenuated18 commands exact normalized match no regression;5 low-level music variants no additional subtitles; known short hallucination remains reported. All synthetic/old-source, no independent confirmation.',
        timing='No fresh P95/UI timing; cached times historical only. Actual new counterexample decoder times descriptive.',
        independent_confirmed=False,last_candidate_in_direction=True)
    pilot.write_new(MANIFEST,m);verify()


def verify():
    require_active();m=pilot.read(MANIFEST)
    for path,sha in m['files'].items():
        if pilot.digest(ROOT/path)!=sha:raise RuntimeError('Frozen source/cache changed: '+path)
    for c in m['cached']:
        if pilot.digest(ROOT/c['input_path'])!=c['input_sha256']:raise RuntimeError('Cached input changed')
    for c in m['fresh']:
        for path,sha in [(c['path'],c['sha256']),(c['gain_path'],c['gain_sha256']),(c['source_path'],c['source_sha256'])]:
            if pilot.digest(ROOT/path)!=sha:raise RuntimeError('Counterexample changed')
    return m


def run():
    if OUTPUT.exists():raise RuntimeError('Already started, zero retry')
    m=verify();limits=pilot.resources()
    if pilot.digest(pilot.MODEL)!=m['model_sha256']:raise RuntimeError('Model changed')
    s=pilot.read(STATE);count=s['candidate_attempts'].get('bounded_input_gain',0)
    if count!=1:raise RuntimeError('This is exactly the second and last gain candidate')
    s['candidate_attempts']['bounded_input_gain']=2
    tmp=STATE.with_suffix('.tmp');tmp.write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n');tmp.replace(STATE)
    from v020_runtime_validation import Protocol,runtime,infer,append
    protocol=Protocol();model=None
    try:
        with OUTPUT.open('x') as f:
            f.write(json.dumps(dict(type='metadata',manifest_sha256=pilot.digest(MANIFEST),resources=limits,
                at=datetime.now().astimezone().isoformat(),scope='Last development gain candidate: cached82 logical rows and46 new synthetic counterexample requests; no independent acceptance'),ensure_ascii=False)+'\n')
        for c in m['cached']:append(OUTPUT,dict(type='cached_result',**c))
        model=runtime();requests=0
        for c in m['fresh']:
            for mode in c['mode_order']:
                require_active()
                input_case=dict(c,path=c['path'] if mode=='baseline' else c['gain_path'])
                row=infer(model,protocol,input_case,'bilingual',m['config']['hints'])
                append(OUTPUT,dict(type='request',index=requests,mode=mode,group=c['group'],**row));requests+=1
        if requests!=46:raise RuntimeError('Request order/count invalid')
        append(OUTPUT,dict(type='complete',new_requests=requests,cached_logical_rows=82,resources=pilot.resources(),at=datetime.now().astimezone().isoformat()))
    except BaseException as error:
        if OUTPUT.exists():append(OUTPUT,dict(type='failure',error=repr(error)))
        raise
    finally:
        if model is not None:model.close()
        protocol.close()


if __name__=='__main__':
    commands={'prepare':prepare,'verify':verify,'run':run}
    if len(sys.argv)!=2 or sys.argv[1] not in commands:raise SystemExit('prepare | verify | run')
    commands[sys.argv[1]]()
