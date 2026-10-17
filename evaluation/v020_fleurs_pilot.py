"""One bounded six-case human-reference pilot; not the incomplete 12-case plan.

prepare/verify never load a model. run refuses prior output and requires all
three audited joint runs, frozen dependencies and an enforced memory cgroup.
Chinese meaning is reviewed against predeclared units, not string similarity.
"""
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import statistics
import sys
import wave

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'evaluation/results/v020-independent'
DATA = OUT / 'fleurs_preflight'
MANIFEST = DATA / 'pilot6_manifest.json'
OUTPUT = DATA / 'pilot6_requests.jsonl'
MODEL = Path('/home/hyh/Tools/litert/models/gemma-4-E2B-it.litertlm')
IDS = [1700, 1750, 1776, 1778, 1791, 1792]
MODES = {'baseline': '', 'domain': 'CS2 broadcast.'}
UNITS = {
    1700: ['同一事物在maria/月海下面较薄', '在highlands/高地下面较厚', '薄厚关系不能倒置'],
    1750: ['这一发现提供认识/了解', '认识涉及羽毛进化', '羽毛属于鸟类'],
    1776: ['在一夜之间', '制成/印刷150到200份', '这些副本现在有特定名称', '名称Dunlap broadsides/邓拉普宽边版，不换成无关实体'],
    1778: ['电视报道显示', '白烟从工厂/设施冒出，不能改为电竞下包/包点'],
    1791: ['否定/禁止破坏遗址', '手段包括在建筑物做标记/刻划涂鸦', '否定作用范围不能倒置为建议涂鸦'],
    1792: ['这一性质称为化学物质的pH', '可以制作指示剂', '使用红甘蓝汁'],
}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def write_new(path, value):
    with Path(path).open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def prepare():
    if MANIFEST.exists() or OUTPUT.exists():
        raise RuntimeError('Already frozen/started; no reselection or implicit retry')
    partial = read(DATA / 'partial_audio_manifest.json')
    if partial['available'] != 6 or partial['original_target'] != 12:
        raise RuntimeError('Unexpected material state')
    cases = sorted(partial['cases'], key=lambda case: case['id'])
    if [case['id'] for case in cases] != IDS:
        raise RuntimeError('Six available IDs changed')
    # Only existing classes are invoked; no compiler, audio inference or SDK engine.
    from v020_runtime_validation import Protocol
    protocol = Protocol()
    try:
        prompts = {mode: dict(zip(['system', 'request'], protocol.prompt('bilingual', hints)))
                   for mode, hints in MODES.items()}
    finally:
        protocol.close()
    joint = read(OUT / 'joint_live_manifest.json')
    dependencies = dict(joint['files'])
    # Preserve actual bridge and transitive local Python source dependencies.
    import ast
    pending = ['v020_fleurs_pilot', 'v020_runtime_validation']
    seen = set()
    while pending:
        module = pending.pop()
        path = ROOT / 'evaluation' / (module + '.py')
        if module in seen or not path.exists():
            continue
        seen.add(module)
        dependencies[str(path.relative_to(ROOT))] = digest(path)
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom) and node.module:
                pending.append(node.module.split('.')[0])
            elif isinstance(node, ast.Import):
                pending.extend(alias.name.split('.')[0] for alias in node.names)
    cp = OUT.parent / 'v020-jvm/protocol-classpath.txt'
    dependencies[str(cp.relative_to(ROOT))] = digest(cp)
    bridge = OUT.parent / 'v020-jvm/V020ProtocolBridge.class'
    dependencies[str(bridge.relative_to(ROOT))] = digest(bridge)
    dependencies['scripts/run-v020-fleurs-pilot'] = digest(ROOT / 'scripts/run-v020-fleurs-pilot')
    for case in cases:
        case['kind'] = 'human_read_speech_parallel_reference'
        case['semantic_units'] = UNITS[case['id']]
    manifest = dict(frozen_at=datetime.now().astimezone().isoformat(),
        original_target=12, original_plan_complete=False, pilot_cases=6,
        pilot_scope='Generic read-speech domain-hint safety/translation diagnostic only; not CS2 positive gain, automatic scene, segmentation, screen latency or product acceptance.',
        missing_original_ids=partial['missing_ids'], cases=cases,
        source_revision='70bb2e84b976b7e960aa89f1c648e09c59f894dd',
        source_url='https://huggingface.co/datasets/google/fleurs',
        attribution='FLEURS: Google; parallel texts: FLORES',
        licenses=['FLEURS CC BY 4.0', 'FLORES text CC BY-SA 4.0'],
        speaker_count='unknown; all six metadata gender labels FEMALE',
        pretraining_contamination='unknown', full_archive_integrity_verified=False,
        original_plan_sha256=digest(DATA / 'control_plan.json'),
        partial_manifest_sha256=digest(DATA / 'partial_audio_manifest.json'),
        joint_manifest_sha256=digest(OUT / 'joint_live_manifest.json'),
        dependencies=dependencies, model_sha256=joint['model_sha256'],
        config=dict(context=768, output=128, threads=4, task='bilingual',
            modes=MODES, prompts=prompts, input='Entire original 3.84-4.92s PCM, no trimming/gain/padding; direct hints, no scene/cadence/history'),
        order=[dict(case_id=case['id'], mode=mode) for index, case in enumerate(cases)
               for mode in (['baseline', 'domain'] if index % 2 == 0 else ['domain', 'baseline'])],
        bounds=dict(requests=12, retries=0, memory_high_bytes=5376*1024*1024,
            memory_max_bytes=6*1024**3, swap_max=0, timeout_seconds=600),
        review=dict(primary='Paired English/Chinese semantic review of 18 predeclared units; explicit per-output evidence and omissions/contradictions/unsupported additions. AI-assisted review is not independent human rating.',
            ratings=['preserved', 'omitted', 'contradicted', 'uncertain'],
            unknown='uncertain remains unresolved, never counted preserved',
            variants='Accept equivalent Chinese expression, word order and numeral words/digits; no reference rewrite after outputs. ID1700 do not require expanding English it to unstated crust. Dunlap transliteration or retained Latin accepted.',
            strict_joint='A delivered subtitle with all units preserved in both languages and no unsupported additions; no_speech/invalid/译文暂不可用 are failures, not removed from denominator6',
            paired='Report gains/losses and new missing/invalid outputs, critical numeric/negation errors and unrelated CS2 insertions on same case; no lexical similarity substitutes for meaning',
            secondary='Literal delivered-English corpus WER, word/numeral rendering can inflate it; timing all12 calls/cold first call and mode medians only descriptive, no screen latency/causal net gain claim',
            official_acceptance_changed=False),
        inference_started=False)
    write_new(MANIFEST, manifest)
    verify()


def verify():
    m = read(MANIFEST)
    if [case['id'] for case in m['cases']] != IDS or len(m['order']) != 12:
        raise RuntimeError('Frozen IDs/order invalid')
    for path, sha in m['dependencies'].items():
        if digest(ROOT / path) != sha:
            raise RuntimeError('Dependency changed: ' + path)
    for name, expected in [('control_plan.json', m['original_plan_sha256']),
                           ('partial_audio_manifest.json', m['partial_manifest_sha256'])]:
        if digest(DATA / name) != expected:
            raise RuntimeError('Reference manifest changed: ' + name)
    if digest(OUT / 'joint_live_manifest.json') != m['joint_manifest_sha256']:
        raise RuntimeError('Joint manifest changed')
    for case in m['cases']:
        for key in ['path', 'original_path']:
            expected = case['sha256' if key == 'path' else 'original_sha256']
            if digest(ROOT / case[key]) != expected:
                raise RuntimeError('Audio changed')
        with wave.open(str(ROOT / case['path'])) as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()) != (1, 2, 16000, case['samples']):
                raise RuntimeError('Audio format/frames changed')
            if hashlib.sha256(wav.readframes(wav.getnframes())).hexdigest() != case['pcm_sha256']:
                raise RuntimeError('PCM changed')
        if case['semantic_units'] != UNITS[case['id']]:
            raise RuntimeError('Rubric changed')
    print(json.dumps(dict(frozen=True, available_cases=6, requests=12,
        semantic_units=sum(len(case['semantic_units']) for case in m['cases']),
        original_plan_complete=False, inference_started=OUTPUT.exists()), ensure_ascii=False), flush=True)
    return m


def require_joint_complete():
    rows = [json.loads(line) for line in (OUT / 'joint_live_series.jsonl').read_text().splitlines()]
    if [(row['run'], row['exit_code']) for row in rows] != [('run1', 0), ('run2', 0), ('run3', 0)]:
        raise RuntimeError('All three audited joint runs must finish successfully first')


def resources():
    line = next(line for line in Path('/proc/self/cgroup').read_text().splitlines() if line.startswith('0::'))
    scope = Path('/sys/fs/cgroup') / line.split('::', 1)[1].lstrip('/')
    limits = {name: (scope / name).read_text().strip() for name in
              ['memory.high', 'memory.max', 'memory.swap.max', 'memory.swap.current', 'memory.events']}
    if limits['memory.max'] == 'max' or int(limits['memory.max']) > 6*1024**3 or limits['memory.swap.max'] != '0':
        raise RuntimeError('Requires finite <=6GiB cgroup and swap0')
    return limits


def run():
    if OUTPUT.exists():
        raise RuntimeError('Pilot already started; no implicit repeat/retry')
    require_joint_complete()
    m = verify()
    limits = resources()
    if digest(MODEL) != m['model_sha256']:
        raise RuntimeError('Model changed')
    from v020_runtime_validation import Protocol, runtime, infer, append
    protocol = Protocol()
    model = None
    try:
        for mode, hints in MODES.items():
            actual = dict(zip(['system', 'request'], protocol.prompt('bilingual', hints)))
            if actual != m['config']['prompts'][mode]:
                raise RuntimeError('Actual product prompt changed')
        with OUTPUT.open('x') as stream:
            stream.write(json.dumps(dict(type='metadata', manifest_sha256=digest(MANIFEST),
                started_at=datetime.now().astimezone().isoformat(), resources=limits,
                scope=m['pilot_scope']), ensure_ascii=False) + '\n')
        model = runtime()
        cases = {case['id']: case for case in m['cases']}
        for index, item in enumerate(m['order']):
            row = infer(model, protocol, cases[item['case_id']], 'bilingual', MODES[item['mode']])
            append(OUTPUT, dict(type='request', index=index, mode=item['mode'], **row))
        append(OUTPUT, dict(type='complete', requests=12, resources=resources(),
            at=datetime.now().astimezone().isoformat()))
    except BaseException as error:
        if OUTPUT.exists():
            append(OUTPUT, dict(type='failure', error=repr(error)))
        raise
    finally:
        if model is not None:
            model.close()
        protocol.close()
    summary()


def summary():
    m = read(MANIFEST)
    rows = [json.loads(line) for line in OUTPUT.read_text().splitlines()]
    requests = [row for row in rows if row['type'] == 'request']
    actual = [(row['case_id'], row['mode']) for row in requests]
    expected = [(row['case_id'], row['mode']) for row in m['order']]
    if rows[-1]['type'] != 'complete' or actual != expected:
        raise RuntimeError('Incomplete/duplicate/reordered pilot; no complete summary')
    from score_reference import words, edit_distance
    cases = {case['id']: case for case in m['cases']}
    groups = {}
    for mode in MODES:
        selected = [row for row in requests if row['mode'] == mode]
        total = sum(len(words(cases[row['case_id']]['reference_en'])) for row in selected)
        errors = sum(edit_distance(words(cases[row['case_id']]['reference_en']), words(row['english'])) for row in selected)
        groups[mode] = dict(cases=6, statuses=dict(Counter(row['status'] for row in selected)),
            literal_reference_words=total, literal_word_errors=errors, literal_wer=errors/total,
            median_ms=statistics.median(row['inference_ms'] for row in selected),
            all_ms=[row['inference_ms'] for row in selected])
    write_new(DATA / 'pilot6_technical_summary.json', dict(complete=True, groups=groups,
        first_call_index=0, timing_scope='Descriptive decoder time only; cold first call included; n6/mode, no p95 claim',
        semantic_review_complete=False, official_acceptance_passed=False,
        original_plan_complete=False, scope=m['pilot_scope']))


if __name__ == '__main__':
    commands = {'prepare': prepare, 'verify': verify, 'run': run, 'summary': summary}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        raise SystemExit('prepare | verify | run | summary')
    commands[sys.argv[1]]()
