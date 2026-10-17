"""No-engine SDK/config/source preflight for one execution-path candidate.

Validate the *requested* configuration and current Kotlin protocol separately
from engine initialization. None means model default, not observed MTP=True.
"""
import ast
from datetime import datetime
import hashlib
import inspect
import json
from pathlib import Path
import subprocess
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'evaluation/results/v020-round3/preflight'
STATE = ROOT/'evaluation/results/v020-convergence/optimization_state.json'
AUTOMATION = Path('/home/hyh/.codex/automations/opencaption/automation.toml')
MODEL = Path('/home/hyh/Tools/litert/models/gemma-4-E2B-it.litertlm')
JAVA = '/home/hyh/Tools/java/eclipse-temurin-jdk17/bin'


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):
            h.update(b)
    return h.hexdigest()


def authorized(state, automation):
    if state.get('status')!='active' or automation.get('status')!='ACTIVE':
        raise RuntimeError('Paused')
    if state.get('current_round')!=3:
        raise RuntimeError('Not current round3')
    if state.get('consecutive_complete_rounds_without_gain',0)>=3:
        raise RuntimeError('Complete-round stop reached')


def requested_config(mode):
    if mode not in ['auto','disabled']:
        raise ValueError('Unknown execution path')
    return dict(model_path=str(MODEL),model_backend='CPU',audio_backend='CPU',
        model_threads=4,audio_threads=4,max_num_tokens=768,max_output_tokens=128,
        cache_mode='disk',top_k=1,top_p=1.0,temperature=0.0,
        thinking=False,task='bilingual',hints='CS2 broadcast.',
        enable_speculative_decoding=None if mode=='auto' else False)


def compare_configs(baseline,candidate):
    changed=[k for k in baseline.keys()|candidate.keys()
             if baseline.get(k)!=candidate.get(k) or
             type(baseline.get(k)) is not type(candidate.get(k))]
    if changed!=['enable_speculative_decoding']:
        raise ValueError('More than one independent variable: '+repr(changed))
    if baseline['enable_speculative_decoding'] is not None or candidate['enable_speculative_decoding'] is not False:
        raise ValueError('Expected autoNone versus explicitFalse')
    return changed


def read(path):
    return json.loads(Path(path).read_text())


def main():
    report_path=OUT/'report.json'
    if report_path.exists():
        raise RuntimeError('Preflight already complete; inspect checkpoint')
    authorized(read(STATE),tomllib.loads(AUTOMATION.read_text()))
    OUT.mkdir(parents=True,exist_ok=True)
    before=read(ROOT/'evaluation/results/v020-round2/scene-denial/source_snapshot.json')
    for path,sha in before['files'].items():
        if digest(ROOT/path)!=sha:
            raise RuntimeError('Current product/source freeze changed: '+path)
    original=read(ROOT/'evaluation/results/v020-round2/noise1/manifest.json')
    if digest(MODEL)!=original['model_sha256']:
        raise RuntimeError('Model changed')

    # Importing the official package/config classes does not instantiate Engine.
    import importlib.metadata
    import litert_lm
    import litert_lm.interfaces as interfaces
    sdk_version=importlib.metadata.version('litert-lm')
    constructor=inspect.getsource(litert_lm.Engine.__init__)
    base_source=inspect.getsource(interfaces.AbstractEngine)
    if 'If None, use the model' not in ' '.join(base_source.split()):
        raise RuntimeError('SDK default semantics must be reviewed')
    if 'self.max_num_tokens' not in constructor or 'self.enable_speculative_decoding is not None' not in constructor:
        raise RuntimeError('SDK configuration path changed')
    if 'litert_lm_engine_settings_set_enable_speculative_decoding' not in constructor:
        raise RuntimeError('No supported explicit setting path')
    tree=ast.parse(inspect.cleandoc(constructor))
    setter_conditions={}
    for node in ast.walk(tree):
        if not isinstance(node,ast.If):
            continue
        calls=[n.func.attr for statement in node.body for n in ast.walk(statement)
               if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
        for setter in ['litert_lm_engine_settings_set_max_num_tokens',
                       'litert_lm_engine_settings_set_enable_speculative_decoding']:
            if setter in calls:
                setter_conditions[setter]=ast.unparse(node.test)
    if setter_conditions!={
        'litert_lm_engine_settings_set_max_num_tokens':'self.max_num_tokens is not None',
        'litert_lm_engine_settings_set_enable_speculative_decoding':'self.enable_speculative_decoding is not None'}:
        raise RuntimeError('Setter paths not independent: '+repr(setter_conditions))
    (OUT/'sdk_engine_constructor.py.txt').write_text(constructor)
    (OUT/'sdk_abstract_engine.py.txt').write_text(base_source)
    baseline=requested_config('auto');candidate=requested_config('disabled')
    changed=compare_configs(baseline,candidate)

    sdk_files={}
    distribution=importlib.metadata.distribution('litert-lm')
    for item in distribution.files or []:
        path=Path(distribution.locate_file(item))
        if path.is_file() and (path.suffix in ['.py','.so'] or path.name in ['METADATA','RECORD']):
            sdk_files[str(path)]=digest(path)

    # Current immutable classes are source-bound to the already tested parser.
    replay=read(ROOT/'evaluation/results/v020-round2/protocol/replay_manifest.json')
    protocol_source='android/app/src/main/kotlin/dev/opencaption/opencaption/E2eProtocol.kt'
    if digest(ROOT/protocol_source)!=replay['product_source_files'][protocol_source]:
        raise RuntimeError('Current parser is no longer the source-bound class snapshot')
    prior_product=read(ROOT/'evaluation/results/v020-independent/scene_final_source_snapshot.json')
    for name,sha in prior_product['files'].items():
        if name.startswith('android/app/src/main/kotlin/') and name!=protocol_source:
            if digest(ROOT/name)!=sha:
                raise RuntimeError('Other native dependencies changed: '+name)
    parent=ROOT/'evaluation/results/v020-round2/protocol'
    cp=(parent/'after-classpath.txt').read_text().strip()
    class_files={}
    for part in cp.split(':'):
        path=Path(part)
        for file in (path.rglob('*.class') if path.is_dir() else [path]):
            class_files[str(file)]=digest(file)
    for name,sha in replay['class_files']['after'].items():
        if digest(parent/name)!=sha:
            raise RuntimeError('Previously frozen class changed')
    bridge=OUT/'bridge';bridge.mkdir()
    subprocess.run([JAVA+'/javac','-J-Xmx64m','--release','17','-cp',cp,
        '-d',str(bridge),str(ROOT/'evaluation/V020ProtocolBridge.java')],check=True,timeout=20)
    classpath=str(bridge)+':'+cp
    (OUT/'classpath.txt').write_text(classpath+'\n')
    from v020_runtime_validation import Protocol
    class CurrentProtocol(Protocol):
        def __init__(self):
            self.process=subprocess.Popen([JAVA+'/java','-Xmx64m','-cp',classpath,
                'V020ProtocolBridge'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    protocol=CurrentProtocol()
    try:
        prompts=dict(zip(['system','request'],protocol.prompt('bilingual','CS2 broadcast.')))
        if prompts!=original['prompts']:
            raise RuntimeError('Current prompt not identical to last baseline')
        protocol_probes=[]
        for raw,expected in [('[NONE]\nEnglish: [NONE]\nChinese: [NONE]','no_speech'),
                             ('[NONE]\nEnglish: Hello\nChinese: 你好','subtitle'),
                             ('English: [NONE]\nChinese: 你好','invalid')]:
            parsed=protocol.parse('bilingual',raw)
            if parsed['status']!=expected:
                raise RuntimeError('Current protocol probe mismatch')
            protocol_probes.append(dict(raw=raw,result=parsed))
    finally:
        protocol.close()

    # Validate source inputs without changing PCM or loading any audio model.
    cases=[]
    for case in original['cases']:
        if digest(ROOT/case['path'])!=case['sha256']:
            raise RuntimeError('Source input changed')
        cases.append({k:case[k] for k in ['id','group','path','sha256','samples']})
    dependencies=dict(before['files'])
    for name in ['evaluation/v020_round3_preflight.py','evaluation/test_v020_round3_preflight.py',
                 'scripts/run-v020-round3-preflight','evaluation/V020ProtocolBridge.java',
                 'evaluation/v020_runtime_validation.py','evaluation/gemma_replay.py',
                 'evaluation/v020_semantic_rating_cache.py']:
        dependencies[name]=digest(ROOT/name)
    from v020_fleurs_pilot import resources
    report=dict(at=datetime.now().astimezone().isoformat(),sdk_version=sdk_version,
        sdk_files=sdk_files,current_files=dependencies,model_path=str(MODEL),
        model_sha256=original['model_sha256'],protocol_classes=class_files,
        bridge_class_sha256=digest(bridge/'V020ProtocolBridge.class'),
        requested_baseline=baseline,requested_candidate=candidate,only_changed=changed,
        sdk_setter_conditions=setter_conditions,configuration_expression_verified=True,
        live_engine_creation_tested=False,effective_auto_state='unknown_model_default_not_queried',
        scope='Installed public SDK source/config and actual current Kotlin prompt/parser only; no native model initialization, quality or screen timing claim',
        kotlin_baseline='E2B filename -> explicit experimental flag true; max context768. Turning it off in future product must not also drop context.',
        python_baseline='None -> model default per installed public SDK. No assumption that default is true.',
        prompts=prompts,protocol_probes=protocol_probes,cases=cases,resources=resources(),
        can_prepare_paired_candidate=True,runtime_compatibility_pending=True,
        maximum_future_requests=82,new_model_requests=0,candidate_attempts_reserved=0,
        initial_introspection_note='Earlier inspect.getsource on generated dataclass __init__ raised OSError; read public class definition instead. No Engine initialized.')
    with report_path.open('x') as f:
        f.write(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['sdk_version','configuration_expression_verified',
        'live_engine_creation_tested','effective_auto_state','can_prepare_paired_candidate',
        'runtime_compatibility_pending','new_model_requests']},ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
