"""Candidate 1: direct bilingual vs serial English ASR and text translation.

Same E2B, PCM, domain hint and predeclared semantic units, development cases.
18 calls maximum, AB/BA per case, no retries or gold supplied to the candidate.
"""
from datetime import datetime
import json
from pathlib import Path
import sys
import time
import tomllib

import v020_fleurs_pilot as pilot
from v020_convergence_g1 import text_infer, TEXT_SYSTEM

ROOT = pilot.ROOT
OUT = ROOT / 'evaluation/results/v020-convergence'
STATE = OUT / 'optimization_state.json'
AUTOMATION = Path('/home/hyh/.codex/automations/opencaption/automation.toml')
MANIFEST = OUT / 'coupling1_manifest.json'
OUTPUT = OUT / 'coupling1_requests.jsonl'
DIRECTION = 'dual_task_coupling'
HINTS = 'CS2 broadcast.'


def authorized(state, automation):
    if state.get('status') != 'active' or automation.get('status') != 'ACTIVE':
        raise RuntimeError('Paused; do not infer')
    if state.get('gates', {}).get('G2') != 'in_progress':
        raise RuntimeError('G2 is not current')
    if state.get('actual_work_seconds_since_verified_gain', 0) >= 21600 or state.get('consecutive_evaluation_packages_without_verified_gain', 0) >= 3:
        raise RuntimeError('Overall no-gain budget exhausted')


def require_active():
    authorized(pilot.read(STATE), tomllib.loads(AUTOMATION.read_text()))


def reserve_candidate(state):
    count = state.get('candidate_attempts', {}).get(DIRECTION, 0)
    if count >= 2:
        raise RuntimeError('Direction candidate budget exhausted')
    state.setdefault('candidate_attempts', {})[DIRECTION] = count + 1
    return state


def prepare():
    require_active()
    if MANIFEST.exists() or OUTPUT.exists():
        raise RuntimeError('Already frozen/started, no implicit retry')
    old = pilot.verify()
    g1 = pilot.read(OUT / 'g1_manifest.json')
    dependencies = dict(g1['dependencies'])
    for name in ['evaluation/v020_coupling_candidate.py', 'scripts/run-v020-coupling-candidate',
                 'evaluation/test_v020_coupling_candidate.py']:
        dependencies[name] = pilot.digest(ROOT / name)
    from v020_runtime_validation import Protocol
    protocol = Protocol()
    try:
        prompts = {task: dict(zip(['system', 'request'], protocol.prompt(task, HINTS)))
                   for task in ['bilingual', 'english']}
    finally:
        protocol.close()
    order = [dict(case_id=c['id'], modes=['baseline', 'dual'] if i % 2 == 0 else ['dual', 'baseline'])
             for i, c in enumerate(old['cases'])]
    pilot.write_new(MANIFEST, dict(frozen_at=datetime.now().astimezone().isoformat(),
        cases=old['cases'], dependencies=dependencies, model_sha256=old['model_sha256'],
        original_pilot_sha256=pilot.digest(pilot.MANIFEST), g1_sha256=pilot.digest(OUT/'g1_manifest.json'),
        order=order, prompts=prompts, text_system=TEXT_SYSTEM,
        config=dict(context=768, output=128, threads=4, hints=HINTS),
        bounds=dict(max_requests=18, retries=0, memory_max_bytes=6*1024**3, swap_max=0, timeout_seconds=600),
        hypothesis='Bilingual joint generation may impair source English. A serial same-model English-only call followed by translation of its actual recognized text may recover source/Chinese meaning.',
        candidate_receives_gold=False, development_previously_observed=True,
        scoring='Reuse original 18 semantic units and equivalent-word rules; per-language preserved/omitted/contradicted/uncertain and full-case denominator6. No output-adaptive reference changes. AI-assisted review, not independent acceptance.',
        continue_gate='Development: at least3 net repaired Chinese units and at least20% fewer lost Chinese units, no complete-case/coverage loss or new critical errors. Independent confirmation still required. Compare both path decoder time sums, with cold first call identified; no n6 P95.',
        latency_screen='Median full-path decoder cost >20% worse flags unsuitable default even with local quality gains; this early rejection does NOT relax formal P95<=5% regression gate.',
        invalid_handling='If English-only output is NONE/invalid, do not translate invented text; record failed dual case and skipped translation. At most18 calls, zero retries.',
        scope='One development candidate, not full CaptionEngine, UI latency, independent CS2 quality or default model switch'))
    verify()


def verify():
    require_active()
    old = pilot.verify()
    m = pilot.read(MANIFEST)
    if m['cases'] != old['cases'] or m['original_pilot_sha256'] != pilot.digest(pilot.MANIFEST) or m['g1_sha256'] != pilot.digest(OUT/'g1_manifest.json'):
        raise RuntimeError('Original material/freeze changed')
    for path, sha in m['dependencies'].items():
        if pilot.digest(ROOT/path) != sha:
            raise RuntimeError('Frozen dependency changed: ' + path)
    return m


def run():
    if OUTPUT.exists():
        raise RuntimeError('Already started; do not repeat')
    m = verify()
    resources = pilot.resources()
    if pilot.digest(pilot.MODEL) != m['model_sha256']:
        raise RuntimeError('Model changed')
    from v020_runtime_validation import Protocol, runtime, infer, append
    protocol = Protocol()
    model = None
    try:
        for task in ['bilingual', 'english']:
            if dict(zip(['system', 'request'], protocol.prompt(task, HINTS))) != m['prompts'][task]:
                raise RuntimeError('Actual prompt changed')
        state = reserve_candidate(pilot.read(STATE))
        temp = STATE.with_suffix('.tmp')
        temp.write_text(json.dumps(state, ensure_ascii=False, indent=2)+'\n')
        temp.replace(STATE)
        with OUTPUT.open('x') as stream:
            stream.write(json.dumps(dict(type='metadata', at=datetime.now().astimezone().isoformat(),
                manifest_sha256=pilot.digest(MANIFEST), resources=resources, scope=m['scope']), ensure_ascii=False)+'\n')
        model = runtime()
        cases = {c['id']: c for c in m['cases']}
        calls = 0
        for item in m['order']:
            case = cases[item['case_id']]
            for mode in item['modes']:
                require_active()
                started = time.monotonic()
                task = 'bilingual' if mode == 'baseline' else 'english'
                row = infer(model, protocol, case, task, HINTS)
                append(OUTPUT, dict(type='request', index=calls, mode=mode, phase=task, **row))
                calls += 1
                if mode == 'baseline':
                    delivered = {key: row[key] for key in ['status', 'english', 'chinese', 'reason']}
                    decoder_ms = row['inference_ms']
                elif row['status'] == 'subtitle':
                    # The candidate receives ONLY actual model English, never reference text.
                    translated = text_infer(model, row['english'])
                    append(OUTPUT, dict(type='request', index=calls, case_id=case['id'],
                        mode=mode, phase='translate_model_english', **translated))
                    calls += 1
                    delivered = protocol.parse('bilingual', 'English: '+row['english']+'\nChinese: '+translated['raw'])
                    decoder_ms = row['inference_ms'] + translated['inference_ms']
                else:
                    delivered = dict(status=row['status'], english='', chinese='', reason='source_unavailable')
                    decoder_ms = row['inference_ms']
                append(OUTPUT, dict(type='pair_result', case_id=case['id'], mode=mode,
                    decoder_ms=decoder_ms, path_elapsed_ms=(time.monotonic()-started)*1000, **delivered))
        if calls > 18:
            raise RuntimeError('Request budget exceeded')
        append(OUTPUT, dict(type='complete', requests=calls, resources=pilot.resources(),
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
