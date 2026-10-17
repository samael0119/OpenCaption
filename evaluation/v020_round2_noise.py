"""Fixed FFT denoising experiment, current Kotlin parser, bounded round2 guard.

Only observed development cases. No gain, voice veto, adaptive selection or
output retry. Explicit 25ms filter latency compensation preserves the tail.
"""
import array
import ast
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys
import time
import tomllib
import wave

import v020_fleurs_pilot as pilot

ROOT = pilot.ROOT
OUT = ROOT / 'evaluation/results/v020-round2/noise1'
STATE = ROOT / 'evaluation/results/v020-convergence/optimization_state.json'
PLAN = ROOT / 'evaluation/results/v020-round2/noise_preflight_plan.json'
MANIFEST = OUT / 'manifest.json'
OUTPUT = OUT / 'requests.jsonl'
AUTOMATION = Path('/home/hyh/.codex/automations/opencaption/automation.toml')
DIRECTION = 'conservative_fft_noise_reduction'
FILTER = 'afftdn=nr=6:nf=-80:tn=1:gs=3'
DELAY = 400  # local impulse measurement: 25ms at16k; fixed before inference
JAVA = '/home/hyh/Tools/java/eclipse-temurin-jdk17/bin/java'


def authorized(state, automation):
    if state.get('status') != 'active' or automation.get('status') != 'ACTIVE':
        raise RuntimeError('Paused')
    if state.get('current_round') != 2 or state.get('current_round_status') != 'in_progress':
        raise RuntimeError('Not current round2')
    if state.get('consecutive_complete_rounds_without_gain', 0) >= 3:
        raise RuntimeError('Complete-round stop reached')
    # Historical small-candidate/time counters explicitly do not stop round2.


def require_active():
    authorized(pilot.read(STATE), tomllib.loads(AUTOMATION.read_text()))


def pcm(path):
    with wave.open(str(path)) as w:
        if (w.getnchannels(), w.getsampwidth(), w.getframerate()) != (1, 2, 16000):
            raise RuntimeError('Expected mono16k PCM16')
        values = array.array('h', w.readframes(w.getnframes()))
    if sys.byteorder != 'little':
        raise RuntimeError('Little endian required')
    return values


def filter_pcm(values, compensate=True):
    # Flush filter's causal delay, then remove ONLY that delay, not source audio.
    sent = values + array.array('h', [0]*DELAY) if compensate else values
    command = ['ffmpeg', '-nostdin', '-hide_banner', '-loglevel', 'error',
               '-threads', '1', '-f', 's16le', '-ar', '16000', '-ac', '1',
               '-i', 'pipe:0', '-af', FILTER, '-f', 's16le', '-c:a',
               'pcm_s16le', 'pipe:1']
    began = time.monotonic()
    result = subprocess.run(command, input=sent.tobytes(), capture_output=True,
                            check=True, timeout=15)
    filtered = array.array('h', result.stdout)
    if len(filtered) != len(sent):
        raise RuntimeError('FFT changed frame count; no implicit repair')
    if compensate:
        filtered = filtered[DELAY:]
    return filtered, (time.monotonic()-began)*1000


class CurrentProtocol:
    def __init__(self):
        from v020_runtime_validation import Protocol
        self._methods = Protocol
        cp = (OUT/'classpath.txt').read_text().strip()
        self.process = subprocess.Popen([JAVA, '-Xmx64m', '-cp', cp,
            'V020ProtocolBridge'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)

    def send(self, command, task, value):
        return self._methods.send(self, command, task, value)

    def prompt(self, task, hints):
        return self._methods.prompt(self, task, hints)

    def parse(self, task, raw):
        return self._methods.parse(self, task, raw)

    def close(self):
        return self._methods.close(self)


def collect_dependencies():
    paths = set()
    # Current product tree is frozen separately; never rewrite old snapshots.
    for directory, pattern in [('lib', '*.dart'), ('android/app/src', '*.kt'),
                               ('assets/corpora', '*.json')]:
        paths.update(ROOT.joinpath(directory).rglob(pattern))
    pending = ['v020_round2_noise', 'v020_runtime_validation', 'v020_fleurs_pilot']
    visited = set()
    while pending:
        module = pending.pop()
        source = ROOT/'evaluation'/(module+'.py')
        if module in visited or not source.exists():
            continue
        visited.add(module); paths.add(source)
        for node in ast.walk(ast.parse(source.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module:
                pending.append(node.module.split('.')[0])
            elif isinstance(node, ast.Import):
                pending.extend(n.name.split('.')[0] for n in node.names)
    paths.update([ROOT/'scripts/run-v020-round2-noise',
                  ROOT/'evaluation/test_v020_round2_noise.py', PLAN, OUT/'classpath.txt'])
    paths.update((OUT/'bridge').rglob('*.class'))
    cp = (OUT/'classpath.txt').read_text().strip().split(':')
    for part in cp[1:]:
        p = Path(part)
        paths.update(p.rglob('*.class') if p.is_dir() else [p])
    return {str(p.relative_to(ROOT)): pilot.digest(p) for p in sorted(paths)}


def prepare():
    require_active()
    if MANIFEST.exists() or OUTPUT.exists():
        raise RuntimeError('Already frozen/started')
    if not (OUT/'classpath.txt').exists():
        raise RuntimeError('Compile isolated current bridge first')
    plan = pilot.read(PLAN)
    if plan['filter'] != FILTER:
        raise RuntimeError('Predeclared filter changed')
    old_path = ROOT/'evaluation/results/v020-convergence/gain1_manifest.json'
    old = pilot.read(old_path)
    cases = []
    for c in old['cases']:
        cases.append({k:v for k,v in c.items() if not k.startswith('gain_') and
                      k not in ['input_peak_pcm','output_peak_pcm','changed']})
    short_path = ROOT/'evaluation/results/v020-convergence/gain2_audio/known-short-window148.wav'
    cases.append(dict(id='known-short-window148', group='known_short_music',
        kind='known_instrumental_music', path=str(short_path.relative_to(ROOT)),
        sha256=pilot.digest(short_path), reference_en='', samples=32000,
        provenance='gain2_manifest cached original run1 window148 reconstruction, including product prepareShort zeros; observed failure'))
    if len(cases) != 41 or dict(Counter(c['group'] for c in cases)) != plan['groups']:
        raise RuntimeError('Fixed set changed')
    (OUT/'audio').mkdir()
    for c in cases:
        p = ROOT/c['path']
        if pilot.digest(p) != c['sha256']:
            raise RuntimeError('Original audio changed')
        original = pcm(p)
        if len(original) != c['samples']:
            raise RuntimeError('Source frame count changed')
        filtered, elapsed = filter_pcm(original)
        destination = OUT/'audio'/(str(c['id'])+'.wav')
        with wave.open(str(destination), 'wb') as w:
            w.setparams((1,2,16000,len(original),'NONE','not compressed'))
            w.writeframes(filtered.tobytes())
        c.update(noise_path=str(destination.relative_to(ROOT)),
            noise_sha256=pilot.digest(destination), source_peak=max(map(abs,original)),
            filtered_peak=max(map(abs,filtered)), filter_cli_ms=elapsed,
            source_nonzero=sum(v!=0 for v in original), filtered_nonzero=sum(v!=0 for v in filtered))
    protocol = CurrentProtocol()
    try:
        prompts = dict(zip(['system','request'],protocol.prompt('bilingual',plan['config']['hints'])))
    finally:
        protocol.close()
    references = [old_path, ROOT/'evaluation/results/v020-convergence/gain2_manifest.json',
                  pilot.MANIFEST, pilot.OUT/'frozen_cases.json',pilot.OUT/'whisper_holdout_cases.json']
    pilot.write_new(MANIFEST, dict(frozen_at=datetime.now().astimezone().isoformat(),
        cases=cases, files=collect_dependencies(), references={str(p.relative_to(ROOT)):pilot.digest(p) for p in references},
        model_sha256=old['model_sha256'], ffmpeg_version=subprocess.check_output(['ffmpeg','-version'],text=True).splitlines()[0],
        config=plan['config'], prompts=prompts, filter=FILTER,
        delay=dict(samples=DELAY,ms=25,policy='append400 exact-zero frames to flush causal filter; discard400 filter-delay frames; original source and tail kept, final frame count identical; streaming cost not measured'),
        order=[dict(case_id=c['id'],modes=['baseline','noise'] if i%2==0 else ['noise','baseline']) for i,c in enumerate(cases)],
        bounds=dict(max_requests=82,retries=0,memory_max_bytes=6*1024**3,swap_max=0,timeout_seconds=600),
        scope='Observed developer fixtures; AI-reviewed Chinese semantics; no independent acceptance, screen end-to-end latency or Android integration',
        scoring=plan['score_policy'],continuation=plan['continuation']))
    verify()


def verify():
    require_active()
    m = pilot.read(MANIFEST)
    for path, sha in {**m['files'], **m['references']}.items():
        if pilot.digest(ROOT/path) != sha:
            raise RuntimeError('Frozen dependency changed: '+path)
    for c in m['cases']:
        for path_key, sha_key in [('path','sha256'),('noise_path','noise_sha256')]:
            if pilot.digest(ROOT/c[path_key]) != c[sha_key] or len(pcm(ROOT/c[path_key])) != c['samples']:
                raise RuntimeError('Audio changed')
    print(json.dumps(dict(frozen=True,cases=len(m['cases']),max_requests=82,files=len(m['files'])),ensure_ascii=False),flush=True)
    return m


def run():
    if OUTPUT.exists():
        raise RuntimeError('Already started; no implicit retry')
    m = verify(); resources = pilot.resources()
    if pilot.digest(pilot.MODEL) != m['model_sha256']:
        raise RuntimeError('Model changed')
    from v020_runtime_validation import runtime, infer, append
    protocol = CurrentProtocol(); model = None
    try:
        if dict(zip(['system','request'],protocol.prompt('bilingual',m['config']['hints']))) != m['prompts']:
            raise RuntimeError('Prompt changed')
        state = pilot.read(STATE)
        count = state['candidate_attempts'].get(DIRECTION,0)
        if count >= 2:
            raise RuntimeError('Direction exhausted')
        state['candidate_attempts'][DIRECTION]=count+1
        state['next_package']='round2_noise_candidate1_in_progress'
        temp=STATE.with_suffix('.tmp');temp.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n');temp.replace(STATE)
        with OUTPUT.open('x') as f:
            f.write(json.dumps(dict(type='metadata',manifest_sha256=pilot.digest(MANIFEST),resources=resources,at=datetime.now().astimezone().isoformat()))+'\n')
        model=runtime();calls=0;cases={c['id']:c for c in m['cases']}
        for item in m['order']:
            c=cases[item['case_id']]
            for mode in item['modes']:
                require_active()
                input_case=dict(c,path=c['path'] if mode=='baseline' else c['noise_path'])
                row=infer(model,protocol,input_case,'bilingual',m['config']['hints'])
                append(OUTPUT,dict(type='request',index=calls,mode=mode,group=c['group'],input_sha256=c['sha256' if mode=='baseline' else 'noise_sha256'],**row));calls+=1
        if calls!=82:
            raise RuntimeError('Wrong request count')
        verify()
        append(OUTPUT,dict(type='complete',requests=calls,resources=pilot.resources(),at=datetime.now().astimezone().isoformat()))
    except BaseException as error:
        if OUTPUT.exists():
            append(OUTPUT,dict(type='failure',error=repr(error)))
        raise
    finally:
        if model is not None:
            model.close()
        protocol.close()


if __name__=='__main__':
    functions={'prepare':prepare,'verify':verify,'run':run}
    if len(sys.argv)!=2 or sys.argv[1] not in functions:
        raise SystemExit('prepare | verify | run')
    functions[sys.argv[1]]()
