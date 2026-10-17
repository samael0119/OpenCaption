"""Bounded G1 diagnosis, with preserved pilot references and a new execution freeze.

12 original AB/BA audio calls plus 6 human-English text diagnostics, one model.
The text arm is a localization aid, not the product audio prompt or a candidate.
Old pilot manifests, entry guards, product sources and failed logs stay intact.
"""
from datetime import datetime
import json
from pathlib import Path
import resource
import sys
import time
import tomllib

import v020_fleurs_pilot as pilot

ROOT = pilot.ROOT
OUT = ROOT / 'evaluation/results/v020-convergence'
STATE = OUT / 'optimization_state.json'
AUTOMATION = Path('/home/hyh/.codex/automations/opencaption/automation.toml')
MANIFEST = OUT / 'g1_manifest.json'
OUTPUT = OUT / 'g1_requests.jsonl'
TEXT_SYSTEM = 'Translate the provided English into simplified Chinese faithfully. Preserve names, numbers and negation. Output only the translation. Do not explain or add unstated facts.'


def authorized(state, automation):
    if state.get('status') != 'active' or automation.get('status') != 'ACTIVE':
        raise RuntimeError('Optimization or automation paused; do not start')
    if state.get('gates', {}).get('G1') != 'in_progress':
        raise RuntimeError('G1 not authorized as current work package')
    if state.get('actual_work_seconds_since_verified_gain', 0) >= 21600:
        raise RuntimeError('No-gain actual-work limit reached')
    if state.get('consecutive_evaluation_packages_without_verified_gain', 0) >= 3:
        raise RuntimeError('No-gain evaluation limit reached')


def require_authorized():
    authorized(pilot.read(STATE), tomllib.loads(AUTOMATION.read_text()))


def prepare():
    require_authorized()
    if MANIFEST.exists() or OUTPUT.exists() or pilot.OUTPUT.exists():
        raise RuntimeError('Already frozen/observed: inspect existing evidence')
    old = pilot.verify()
    dependencies = dict(old['dependencies'])
    for name in ['evaluation/v020_convergence_g1.py', 'scripts/run-v020-convergence-g1',
                 'evaluation/test_v020_convergence_g1.py']:
        dependencies[name] = pilot.digest(ROOT / name)
    order = [dict(case_id=r['case_id'], mode=r['mode'], modality='audio') for r in old['order']]
    order += [dict(case_id=c['id'], mode='text_reference', modality='text') for c in old['cases']]
    pilot.write_new(MANIFEST, dict(frozen_at=datetime.now().astimezone().isoformat(),
        original_pilot_sha256=pilot.digest(pilot.MANIFEST), dependencies=dependencies,
        model_sha256=old['model_sha256'], cases=old['cases'], config=old['config'],
        review=old['review'], text_system=TEXT_SYSTEM, order=order,
        bounds=dict(requests=18, audio_requests=12, text_requests=6, retries=0,
                    memory_max_bytes=6*1024**3, swap_max=0, timeout_seconds=600),
        scope='Exploratory G1: six general human references, AI-assisted review; not independent CS2 quality, a candidate optimization, product text route or screen timing.',
        interpretation='Compare missing/misheard English vs Chinese semantic loss. Text success cannot causally prove acoustics are the sole cause: modality/system differ. All six text cases preselected, no output-adaptive calls.'))
    verify()


def verify():
    require_authorized()
    old = pilot.verify()
    m = pilot.read(MANIFEST)
    if m['original_pilot_sha256'] != pilot.digest(pilot.MANIFEST):
        raise RuntimeError('Original freeze changed')
    if m['cases'] != old['cases'] or m['config'] != old['config'] or m['review'] != old['review']:
        raise RuntimeError('Reference/config/rubric changed')
    if len(m['order']) != 18 or m['text_system'] != TEXT_SYSTEM:
        raise RuntimeError('Request limit or text instruction changed')
    for path, sha in m['dependencies'].items():
        if pilot.digest(ROOT / path) != sha:
            raise RuntimeError('Frozen dependency changed: ' + path)
    return m


def text_infer(model, reference):
    from gemma_replay import response_text
    api = model.api
    started = time.monotonic()
    with model.engine.create_conversation(system_message=TEXT_SYSTEM,
            thinking_config=api.ThinkingConfig(False, 0),
            sampler_config=api.SamplerConfig(top_k=1, top_p=1.0, temperature=0.0),
            max_output_tokens=128) as conversation:
        response = conversation.send_message(api.Contents.of(reference),
            max_output_tokens=128, thinking_config=api.ThinkingConfig(False, 0))
    return dict(raw=response_text(response), inference_ms=(time.monotonic()-started)*1000,
                reference_input=reference, peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)


def run():
    if OUTPUT.exists() or pilot.OUTPUT.exists():
        raise RuntimeError('Already started/observed; zero implicit retry')
    m = verify()
    limits = pilot.resources()
    if pilot.digest(pilot.MODEL) != m['model_sha256']:
        raise RuntimeError('Model changed')
    from v020_runtime_validation import Protocol, runtime, infer, append
    protocol = Protocol()
    model = None
    try:
        for mode, hints in pilot.MODES.items():
            if dict(zip(['system', 'request'], protocol.prompt('bilingual', hints))) != m['config']['prompts'][mode]:
                raise RuntimeError('Actual product prompt changed')
        with OUTPUT.open('x') as stream:
            stream.write(json.dumps(dict(type='metadata', manifest_sha256=pilot.digest(MANIFEST),
                at=datetime.now().astimezone().isoformat(), resources=limits, scope=m['scope']), ensure_ascii=False)+'\n')
        model = runtime()
        cases = {c['id']: c for c in m['cases']}
        for index, item in enumerate(m['order']):
            require_authorized()
            case = cases[item['case_id']]
            if item['modality'] == 'audio':
                row = infer(model, protocol, case, 'bilingual', pilot.MODES[item['mode']])
            else:
                row = dict(case_id=case['id'], **text_infer(model, case['reference_en']))
            append(OUTPUT, dict(type='request', index=index, mode=item['mode'], modality=item['modality'], **row))
        append(OUTPUT, dict(type='complete', requests=18, resources=pilot.resources(),
                           at=datetime.now().astimezone().isoformat()))
    except BaseException as error:
        if OUTPUT.exists():
            append(OUTPUT, dict(type='failure', error=repr(error)))
        raise
    finally:
        if model is not None:
            model.close()
        protocol.close()


if __name__ == '__main__':
    commands = {'prepare': prepare, 'verify': verify, 'run': run}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        raise SystemExit('prepare | verify | run')
    commands[sys.argv[1]]()
