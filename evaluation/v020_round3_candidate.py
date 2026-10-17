"""Candidate1: current auto call configuration vs explicit speculation-off.

41 paired observed cases,82 calls,3 serial model lifetimes, no answer retries.
The auto model's effective internal speculation state remains unobserved.
"""
import ast
from collections import defaultdict
from datetime import datetime
import gc
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import tomllib
from types import SimpleNamespace

import v020_fleurs_pilot as pilot
from v020_round3_preflight import authorized, requested_config, compare_configs

ROOT=pilot.ROOT
OUT=ROOT/'evaluation/results/v020-round3/candidate1'
PREFLIGHT=ROOT/'evaluation/results/v020-round3/preflight'
STATE=ROOT/'evaluation/results/v020-convergence/optimization_state.json'
AUTOMATION=Path('/home/hyh/.codex/automations/opencaption/automation.toml')
MANIFEST=OUT/'manifest.json'
OUTPUT=OUT/'requests.jsonl'
DIRECTION='speculative_decoding_execution_path'


def require_active():
    authorized(pilot.read(STATE),tomllib.loads(AUTOMATION.read_text()))


def blocks_for(cases):
    groups=defaultdict(int);ab=[];ba=[]
    for case in cases:
        (ab if groups[case['group']]%2==0 else ba).append(case['id'])
        groups[case['group']]+=1
    return [dict(mode='auto',case_ids=ab),dict(mode='disabled',case_ids=ab+ba),
            dict(mode='auto',case_ids=ba)]


def runtime_args(mode):
    c=requested_config(mode)
    return SimpleNamespace(model=Path(c['model_path']),threads=c['model_threads'],
        max_new_tokens=c['max_output_tokens'],hints='',task=c['task'],
        task_profile='baseline',system_profile='minimal',cache_mode=c['cache_mode'],
        speculative_decoding='default' if mode=='auto' else 'false',
        max_context_tokens=c['max_num_tokens'])


def execute_blocks(blocks,create,consume,close):
    for index,block in enumerate(blocks):
        model=create(block['mode'],index)
        try:
            for offset,case_id in enumerate(block['case_ids']):
                consume(model,case_id,block['mode'],index,offset)
        finally:
            # A close failure aborts before allocating another engine.
            close(model,index)
            del model
            gc.collect()


class CurrentProtocol:
    def __init__(self):
        from v020_runtime_validation import Protocol
        self._methods=Protocol
        cp=(PREFLIGHT/'classpath.txt').read_text().strip()
        self.process=subprocess.Popen(['/home/hyh/Tools/java/eclipse-temurin-jdk17/bin/java',
            '-Xmx64m','-cp',cp,'V020ProtocolBridge'],stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,text=True)

    def send(self,*args): return self._methods.send(self,*args)
    def prompt(self,*args): return self._methods.prompt(self,*args)
    def parse(self,*args): return self._methods.parse(self,*args)
    def close(self): return self._methods.close(self)


def dependencies(pre):
    files=dict(pre['current_files'])
    pending=['v020_round3_candidate','v020_round3_candidate_summary']
    seen=set()
    while pending:
        module=pending.pop();path=ROOT/'evaluation'/(module+'.py')
        if module in seen or not path.exists(): continue
        seen.add(module);files[str(path.relative_to(ROOT))]=pilot.digest(path)
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node,ast.ImportFrom) and node.module:
                pending.append(node.module.split('.')[0])
            elif isinstance(node,ast.Import):
                pending.extend(v.name.split('.')[0] for v in node.names)
    for name in ['evaluation/test_v020_round3_candidate.py','scripts/run-v020-round3-candidate',
                 'evaluation/results/v020-round3/preflight/report.json',
                 'evaluation/results/v020-round3/preflight/classpath.txt']:
        files[name]=pilot.digest(ROOT/name)
    files[str((PREFLIGHT/'bridge/V020ProtocolBridge.class').relative_to(ROOT))]=pilot.digest(PREFLIGHT/'bridge/V020ProtocolBridge.class')
    return files


def prepare():
    require_active()
    if MANIFEST.exists() or OUTPUT.exists(): raise RuntimeError('Already frozen/started')
    OUT.mkdir(parents=True,exist_ok=True)
    pre=pilot.read(PREFLIGHT/'report.json')
    if not pre['can_prepare_paired_candidate'] or pre['new_model_requests']!=0:
        raise RuntimeError('Preflight not suitable')
    for path,sha in {**pre['current_files'],**pre['sdk_files'],**pre['protocol_classes']}.items():
        if pilot.digest(ROOT/path)!=sha: raise RuntimeError('Preflight dependency changed: '+path)
    old_path=ROOT/'evaluation/results/v020-round2/noise1/manifest.json'
    old=pilot.read(old_path)
    cases=[]
    for c in old['cases']:
        case={k:v for k,v in c.items() if not k.startswith('noise_') and
              k not in ['filtered_peak','filtered_nonzero','filter_cli_ms']}
        if pilot.digest(ROOT/case['path'])!=case['sha256']: raise RuntimeError('PCM source changed')
        cases.append(case)
    if len(cases)!=41: raise RuntimeError('Wrong case count')
    # Authoritative frozen review reuse: audio G1 records plus noise candidate.
    g1_path=ROOT/'evaluation/results/v020-convergence/g1_semantic_review.json'
    records=[r for r in pilot.read(g1_path) if r['english_ratings'] is not None]
    prior_path=ROOT/'evaluation/results/v020-round2/noise1/semantic_review_consistent.json'
    prior=pilot.read(prior_path)
    prior_output=ROOT/'evaluation/results/v020-round2/noise1/requests.jsonl'
    prior_rows=[json.loads(l) for l in prior_output.read_text().splitlines()]
    by_id={str(c['id']):c for c in cases}
    for row in prior_rows:
        key=str(row.get('case_id'))
        if row.get('type')!='request' or row.get('mode')!='noise' or key not in prior['cases']: continue
        records.append(dict(case_id=row['case_id'],raw_sha256=hashlib.sha256(row['raw'].encode()).hexdigest(),
            actual_raw=row['raw'],semantic_units=by_id[key]['semantic_units'],
            english_ratings=prior['cases'][key]['noise']['en'],chinese_ratings=prior['cases'][key]['noise']['zh'],
            provenance='prior_noise_consistent_AI_review_not_independent'))
    pilot.write_new(OUT/'frozen_ratings.json',records)
    compare_configs(requested_config('auto'),requested_config('disabled'))
    protocol=CurrentProtocol()
    try: prompts=dict(zip(['system','request'],protocol.prompt('bilingual','CS2 broadcast.')))
    finally: protocol.close()
    if prompts!=pre['prompts']: raise RuntimeError('Prompt changed')
    files=dependencies(pre)
    for path in [old_path,g1_path,prior_path,prior_output,OUT/'frozen_ratings.json']:
        files[str(path.relative_to(ROOT))]=pilot.digest(path)
    pilot.write_new(MANIFEST,dict(at=datetime.now().astimezone().isoformat(),
        hypothesis='A supported opt-out of speculative execution may affect compatibility/quality or cost. Unknown; old JSON+MTP fault does not prove current ASR causality.',
        scope='Observed development cases; no independent source acceptance, physical display timing or Android performance.',
        files=files,sdk_files=pre['sdk_files'],protocol_classes=pre['protocol_classes'],
        model_sha256=pre['model_sha256'],cases=cases,blocks=blocks_for(cases),
        requested_configs={mode:requested_config(mode) for mode in ['auto','disabled']},
        prompts=prompts,only_changed='enable_speculative_decoding None(model default) vsFalse',
        effective_auto_state='unknown; never inferTrue fromNone',
        bounds=dict(requests=82,maximum_engine_loads=3,retries=0,memory_max_bytes=6*1024**3,swap_max=0,timeout_seconds=600),
        metrics='Frozen semantic units/frozen exact-raw judgments; new output AI-assisted review explicit. Whisper strict command, ordinary sourceWER, music fabricated subtitle, paired gains/losses and coverage; no n6P95/real display claim.',
        continuation='>=5pp semantic gain or>=20% target-error reduction and>=3net repairs; all coverage/overall/critical-error guards and formalP95<=5% regression. Independent confirmation required before default integration.',
        order_note='Within each group alternate AB/BA. A=auto, B=disabled; A(AB cases),B(AB+BA),A(BA cases),one engine resident; identify first request of each load as cold.',
        initialization_note='Native Engine compatibility not previously tested. Failure is engineering, not a completed quality round; preserve all started/returned calls, no answer retry.'))
    verify()


def verify():
    require_active();m=pilot.read(MANIFEST)
    for path,sha in {**m['files'],**m['sdk_files'],**m['protocol_classes']}.items():
        if pilot.digest(ROOT/path)!=sha: raise RuntimeError('Frozen dependency changed: '+path)
    for c in m['cases']:
        if pilot.digest(ROOT/c['path'])!=c['sha256']: raise RuntimeError('Frozen PCM changed')
    compare_configs(m['requested_configs']['auto'],m['requested_configs']['disabled'])
    if m['blocks']!=blocks_for(m['cases']): raise RuntimeError('Order changed')
    if sum(len(b['case_ids']) for b in m['blocks'])!=82: raise RuntimeError('Request limit')
    print(json.dumps(dict(frozen=True,cases=41,requests=82,engine_loads=3,files=len(m['files'])),ensure_ascii=False),flush=True)
    return m


def resources():
    r=pilot.resources()
    line=next(l for l in Path('/proc/self/cgroup').read_text().splitlines() if l.startswith('0::'))
    cg=Path('/sys/fs/cgroup')/line.split('::',1)[1].lstrip('/')
    for field in ['memory.current','memory.peak']:
        r[field]=(cg/field).read_text().strip()
    return r


def run():
    if OUTPUT.exists(): raise RuntimeError('Already started; no implicit retry')
    m=verify();limits=resources()
    if pilot.digest(pilot.MODEL)!=m['model_sha256']: raise RuntimeError('Model changed')
    from gemma_replay import LiteRtRuntime
    from v020_runtime_validation import infer,append
    protocol=CurrentProtocol();cases={c['id']:c for c in m['cases']}
    calls=0;reserved=False;stage='before_engine';live=False
    try:
        if dict(zip(['system','request'],protocol.prompt('bilingual','CS2 broadcast.')))!=m['prompts']:
            raise RuntimeError('Prompt changed')
        with OUTPUT.open('x') as f:
            f.write(json.dumps(dict(type='metadata',manifest_sha256=pilot.digest(MANIFEST),
                resources=limits,at=datetime.now().astimezone().isoformat()),ensure_ascii=False)+'\n')

        def create(mode,block_index):
            nonlocal stage,live
            require_active()
            if live: raise RuntimeError('Previous model still live')
            stage='engine_initialization'
            append(OUTPUT,dict(type='engine_initializing',block=block_index,mode=mode,
                requested_config=m['requested_configs'][mode]))
            began=time.monotonic();model=LiteRtRuntime(runtime_args(mode));live=True
            expected=m['requested_configs'][mode]
            actual=dict(max_num_tokens=model.engine.max_num_tokens,
                enable_speculative_decoding=model.engine.enable_speculative_decoding,
                model_threads=model.engine.backend.thread_count,
                audio_threads=model.engine.audio_backend.thread_count,
                max_output_tokens=model.max_new_tokens)
            try:
                for key,value in actual.items():
                    if value!=expected[key] or type(value) is not type(expected[key]):
                        raise RuntimeError('Actual requested Engine field mismatch: '+key)
            except BaseException:
                model.close();live=False;raise
            append(OUTPUT,dict(type='engine_initialized',block=block_index,mode=mode,
                initialization_ms=(time.monotonic()-began)*1000,actual_requested_fields=actual,
                effective_speculation_state='unobserved',resources=resources()))
            return model

        def consume(model,case_id,mode,block_index,offset):
            nonlocal calls,reserved,stage
            require_active()
            if calls>=82: raise RuntimeError('Request budget exhausted')
            if not reserved:
                s=pilot.read(STATE);count=s['candidate_attempts'].get(DIRECTION,0)
                if count>=2: raise RuntimeError('Direction exhausted')
                s['candidate_attempts'][DIRECTION]=count+1;s['current_round_status']='in_progress';s['next_package']='round3_candidate1_inference_in_progress'
                tmp=STATE.with_suffix('.tmp');tmp.write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n');tmp.replace(STATE);reserved=True
            c=cases[case_id];stage='request'
            append(OUTPUT,dict(type='request_started',index=calls,case_id=case_id,mode=mode,block=block_index))
            row=infer(model,protocol,c,'bilingual','CS2 broadcast.')
            append(OUTPUT,dict(type='request',index=calls,mode=mode,block=block_index,
                cold_after_load=offset==0,group=c['group'],input_sha256=c['sha256'],**row));calls+=1

        def close(model,block_index):
            nonlocal live,stage
            try: model.close()
            except BaseException:
                stage='engine_close';raise
            live=False
            append(OUTPUT,dict(type='engine_closed',block=block_index,resources=resources()))

        execute_blocks(m['blocks'],create,consume,close)
        stage='final_verification'
        if calls!=82: raise RuntimeError('Incomplete call count')
        verify()
        append(OUTPUT,dict(type='complete',requests=calls,engine_loads=3,resources=resources(),at=datetime.now().astimezone().isoformat()))
    except BaseException as error:
        if OUTPUT.exists(): append(OUTPUT,dict(type='failure',stage=stage,returned_requests=calls,error=repr(error),engineering_failure=True))
        raise
    finally:
        protocol.close()


if __name__=='__main__':
    commands={'prepare':prepare,'verify':verify,'run':run}
    if len(sys.argv)!=2 or sys.argv[1] not in commands: raise SystemExit('prepare | verify | run')
    commands[sys.argv[1]]()
