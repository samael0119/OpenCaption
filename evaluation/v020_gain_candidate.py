"""One bounded signal-gain candidate; no voice veto, trim, clipping or gold edits."""
import array
from datetime import datetime
import json
import math
from pathlib import Path
import sys
import wave

import v020_fleurs_pilot as pilot
from v020_coupling_candidate import require_active

ROOT = pilot.ROOT
OUT = ROOT / 'evaluation/results/v020-convergence'
STATE = OUT / 'optimization_state.json'
MANIFEST = OUT / 'gain1_manifest.json'
OUTPUT = OUT / 'gain1_requests.jsonl'
DIRECTION = 'bounded_input_gain'


def boost(samples):
    peak = max((abs(v) for v in samples), default=0)
    gain = min(16.0, max(1.0, 0.9 * 32767 / peak)) if peak else 1.0
    return array.array('h', (round(v * gain) for v in samples)), gain


def prepare():
    require_active()
    if MANIFEST.exists() or OUTPUT.exists():
        raise RuntimeError('Already frozen/started; inspect checkpoint')
    old = pilot.verify()
    controls_path = pilot.OUT / 'frozen_cases.json'
    whisper_path = pilot.OUT / 'whisper_holdout_cases.json'
    controls = pilot.read(controls_path)['cases']
    cases = [dict(c, group='fleurs_semantic') for c in old['cases']]
    cases += [dict(c, group='natural_whisper') for c in pilot.read(whisper_path)['cases']]
    cases += [dict(c, group='music') for c in controls if c['kind'] == 'instrumental_music']
    cases += [dict(c, group='ordinary') for c in controls if c['kind'] == 'published_read_speech']
    if len(cases) != 40 or len({c['id'] for c in cases}) != 40:
        raise RuntimeError('Unexpected fixed case set')
    audio_dir = OUT / 'gain1_audio'
    audio_dir.mkdir()
    for case in cases:
        original = ROOT / case['path']
        if pilot.digest(original) != case['sha256']:
            raise RuntimeError('Original audio changed')
        with wave.open(str(original)) as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) != (1, 2, 16000):
                raise RuntimeError('Unexpected PCM format')
            pcm = array.array('h', wav.readframes(wav.getnframes()))
        if sys.byteorder != 'little':
            raise RuntimeError('Requires little endian PCM')
        boosted, gain = boost(pcm)
        target = audio_dir / (str(case['id']) + '.wav')
        with wave.open(str(target), 'wb') as wav:
            wav.setparams((1, 2, 16000, len(pcm), 'NONE', 'not compressed'))
            wav.writeframes(boosted.tobytes())
        case['gain_path'] = str(target.relative_to(ROOT))
        case['gain_sha256'] = pilot.digest(target)
        case['gain_factor'] = gain
        case['gain_db'] = 20*math.log10(gain)
        case['input_peak_pcm'] = max(map(abs, pcm))
        case['output_peak_pcm'] = max(map(abs, boosted))
        case['samples'] = len(pcm)
        case['changed'] = pcm != boosted
    dependencies = dict(pilot.read(OUT/'coupling1_manifest.json')['dependencies'])
    for name in ['evaluation/v020_gain_candidate.py', 'scripts/run-v020-gain-candidate',
                 'evaluation/test_v020_gain_candidate.py']:
        dependencies[name] = pilot.digest(ROOT/name)
    pilot.write_new(MANIFEST, dict(frozen_at=datetime.now().astimezone().isoformat(),
        cases=cases, dependencies=dependencies, model_sha256=old['model_sha256'],
        references={str(controls_path.relative_to(ROOT)): pilot.digest(controls_path),
                    str(whisper_path.relative_to(ROOT)): pilot.digest(whisper_path),
                    str(pilot.MANIFEST.relative_to(ROOT)): pilot.digest(pilot.MANIFEST)},
        config=dict(context=768, output=128, threads=4, hints='CS2 broadcast.'),
        order=[dict(case_id=c['id'], modes=['baseline', 'gain'] if i % 2 == 0 else ['gain', 'baseline']) for i,c in enumerate(cases)],
        bounds=dict(max_requests=80, retries=0, timeout_seconds=600, memory_max_bytes=6*1024**3, swap_max=0),
        transformation='Multiply each PCM16 sample by min(16, max(1, .9*32767/peak)); round once. Preserve all frames, exact zeros, channels, rate and boundaries. No gain for zero/no headroom. No clipping or speech rejection.',
        scoring='FLEURS original18 unit/6case rubric, AI-assisted observed development set; whisper complete command exact normalized word match; ordinary source WER; music any subtitle vsNoSpeech. No independent acceptance.',
        continue_gate='FLEURS >=3 net repaired Chinese units and >=20% fewer lost units, no complete-case loss/new critical errors; whisper strict command and ordinary WER no regression; music no additional visible fabrications. No P95/screen acceptance from n6.',
        unchanged_input='If gain factor1 makes identical PCM, infer baseline once and record explicitly reused unchanged gain result; count actual requests <=80, do not invent separate measurements.',
        independent_confirmed=False))
    verify()


def verify():
    require_active()
    m = pilot.read(MANIFEST)
    for path, sha in {**m['dependencies'], **m['references']}.items():
        if pilot.digest(ROOT/path) != sha:
            raise RuntimeError('Frozen dependency/reference changed: ' + path)
    for case in m['cases']:
        for key, sha in [('path','sha256'),('gain_path','gain_sha256')]:
            if pilot.digest(ROOT/case[key]) != case[sha]:
                raise RuntimeError('Frozen audio changed')
    return m


def run():
    if OUTPUT.exists():
        raise RuntimeError('Already started; zero retry')
    m = verify()
    limits = pilot.resources()
    if pilot.digest(pilot.MODEL) != m['model_sha256']:
        raise RuntimeError('Model changed')
    state = pilot.read(STATE)
    count = state['candidate_attempts'].get(DIRECTION, 0)
    if count >= 2:
        raise RuntimeError('Direction budget exhausted')
    state['candidate_attempts'][DIRECTION] = count + 1
    tmp=STATE.with_suffix('.tmp'); tmp.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n');tmp.replace(STATE)
    from v020_runtime_validation import Protocol, runtime, infer, append
    protocol = Protocol(); model = None
    try:
        with OUTPUT.open('x') as f:
            f.write(json.dumps(dict(type='metadata', at=datetime.now().astimezone().isoformat(),
                manifest_sha256=pilot.digest(MANIFEST), resources=limits,
                scope='Observed development/control fixtures, candidate1; no independent quality or screen latency'),ensure_ascii=False)+'\n')
        model = runtime(); count = 0
        cases = {c['id']:c for c in m['cases']}
        for item in m['order']:
            c = cases[item['case_id']]
            if not c['changed']:
                modes=['baseline']
            else:
                modes=item['modes']
            for mode in modes:
                require_active()
                input_case=dict(c, path=c['path'] if mode=='baseline' else c['gain_path'])
                row=infer(model,protocol,input_case,'bilingual','CS2 broadcast.')
                append(OUTPUT,dict(type='request', index=count, mode=mode, group=c['group'], **row));count+=1
                if not c['changed']:
                    append(OUTPUT,dict(type='unchanged_reuse', source_index=count-1, mode='gain', group=c['group'], **row))
        if count>80:raise RuntimeError('Request limit exceeded')
        append(OUTPUT,dict(type='complete',requests=count,resources=pilot.resources(),at=datetime.now().astimezone().isoformat()))
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
