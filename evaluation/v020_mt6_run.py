"""Frozen36-case translation screen; cached baselines, batches<=10, no retries."""
import gc
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import time
import tomllib

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evaluation/results/v020-mt6'
STATE=ROOT/'evaluation/results/v020-continuation/state.json'
AUTO=Path('/home/hyh/.codex/automations/opencaption/automation.toml')
CONFIG=dict(beam_size=4,max_decoding_length=128,max_input_tokens=512,
            length_penalty=1.0,intra_threads=4,inter_threads=1,device='cpu',compute_type='int8')


def read(p):return json.loads(p.read_text())


def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for c in iter(lambda:f.read(1048576),b''):h.update(c)
    return h.hexdigest()


def authorized(s,a,q,now):
    if s['status']!='active' or s['current_round']!=6 or a['status']!='ACTIVE':raise RuntimeError('Round6 inactive')
    used=q.get('usedPercent')
    if q.get('windowDurationMins')!=10080 or not isinstance(used,(int,float)) or isinstance(used,bool) or not 0<=used<=60:raise RuntimeError('Quota unknown/below40%')
    if not 0<=now-q['observed_at_unix']<=120:raise RuntimeError('Quota stale/future')


def active():authorized(read(STATE),tomllib.loads(AUTO.read_text()),read(OUT/'quota.json'),time.time())


def resources():
    line=next(x for x in Path('/proc/self/cgroup').read_text().splitlines() if x.startswith('0::'))
    cg=Path('/sys/fs/cgroup')/line.split('::',1)[1].lstrip('/')
    d={n:(cg/n).read_text().strip() for n in ['memory.max','memory.swap.max','memory.swap.current','memory.peak','memory.events']}
    if d['memory.max']=='max' or int(d['memory.max'])>6*1024**3 or d['memory.swap.max']!='0' or d['memory.swap.current']!='0':raise RuntimeError('Unbounded memory/swap')
    return d


def model_input(text,sp):
    # Frozen inputs are ASCII. Official unicode-punctuation/nonprinting filters
    # would not change them; reject rather than silently approximate new inputs.
    if not text.isascii() or any(ord(c)<32 for c in text):raise ValueError('Unfrozen normalization required')
    tokens=['>>cmn_Hans<<']+sp.encode(' '.join(text.split()),out_type=str)
    if len(tokens)+1>CONFIG['max_input_tokens']:raise ValueError('Input budget exceeded; never truncate')
    return tokens  # config add_source_eos=true; no duplicate manual EOS


def append(path,row):
    with path.open('a') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush()


def prepare():
    active();resources()
    m=read(ROOT/'evaluation/results/v020-hybrid/translation_manifest.json')
    textrows={}
    for n in range(3):
        for r in map(json.loads,(ROOT/f'evaluation/results/v020-hybrid/translation_batch{n}.jsonl').read_text().splitlines()):
            if r['type']=='request':textrows[str(r['case_id'])]=r
    units={
      '1272-128104-0001':['Quilter named','manner no less interesting than subject matter; do not invert comparison'],
      '1272-128104-0014':['authorship Harry Quilter','M.A. credential retained (literal M A acceptable, no invented degree)'],
      '1272-135031-0003':['girl had been asleep','heard knocking','opened door'],
      '1272-135031-0004':['king fled in disgrace (not avoided disgrace)','friends asking for/looking for addressee'],
      '1272-135031-0005':['speaker begged Ruggedo long ago','send him away','Ruggedo would not/refused; did not do accepted as existing frozen case rule'],
      '1272-135031-0006':['offered help brother escape','brother would not go; willingness retained (existing stricter case rule retained, sensitivity separate)'],
      '1272-135031-0007':['eats and sleeps steadily','new king is speaker of reply','no added drinking'],
      '1272-135031-0008':['speaker hopes he does not work too hard','Shaggy attribution','no inverted negation'],
      '1272-135031-0009':['he does not work at all'],
      '1272-135031-0011':['not exactly','Kaliko replied (returned is dialogue, not physical return)'],
      '1272-135031-0012':['where is my brother now','no unsupported older/younger qualification'],
      '1272-135031-0013':['Shaggy is the inquirer','in metal forest','name identity retained']}
    cases=[]
    for c in m['cases']:
        key=str(c['id']);b=textrows[key];assert b['input_text']==c['input_text']
        cases.append(dict(id=c['id'],group=c['group'],source_role='actual_recognized_text',input_text=c['input_text'],reference_en=c['reference_en'],reference_zh=None,
            baseline_text_translation=b['raw'],baseline_audio_translation=c['baseline']['chinese'],
            semantic_units=units.get(key,[f"Word/command meaning: {c['reference_en']}; synonymous translation allowed; no unrelated entity/action"])))
    g1=read(ROOT/'evaluation/results/v020-convergence/g1_manifest.json')
    g1rows={str(r['case_id']):r for r in map(json.loads,(ROOT/'evaluation/results/v020-convergence/g1_requests.jsonl').read_text().splitlines()) if r.get('modality')=='text'}
    for c in g1['cases']:
        cases.append(dict(id='control-'+str(c['id']),original_id=c['id'],group='gold_source_text_control',source_role='human_reference_diagnostic_not_product_audio',input_text=c['reference_en'],reference_en=c['reference_en'],reference_zh=c['reference_zh'],semantic_units=c['semantic_units'],baseline_text_translation=g1rows[str(c['id'])]['raw']))
    assert len(cases)==36 and all(c['input_text'].isascii() for c in cases)
    from v020_mt6_convert import OUT as ignored  # dependency constants only, no conversion/main
    sys.path.insert(0,str(ROOT/'evaluation/results/s0-20261013/deps'));sys.path.insert(0,str(OUT/'deps'))
    import sentencepiece as spm,yaml
    sp=spm.SentencePieceProcessor(model_file=str(OUT/'original/source.spm'))
    vocab=yaml.safe_load((OUT/'original/opus.spm32k-spm32k.vocab.yml').read_text());assert vocab['>>cmn_Hans<<']==5
    assert read(OUT/'ct2-int8/config.json')['add_source_eos'] is True
    for c in cases:c['input_tokens']=len(model_input(c['input_text'],sp))+1
    files=dict(read(OUT/'conversion.json')['files'])
    files.update({r['path']:r['sha256'] for r in read(OUT/'original_inventory.json')})
    for name in ['evaluation/v020_mt6_run.py','evaluation/v020_mt6_convert.py','evaluation/test_v020_mt6_run.py','scripts/run-v020-mt6',
                 'evaluation/results/v020-hybrid/translation_manifest.json','evaluation/results/v020-hybrid/candidate2_chinese_review.json',
                 'evaluation/results/v020-convergence/g1_manifest.json','evaluation/results/v020-convergence/g1_requests.jsonl',
                 'evaluation/results/v020-hybrid/translation_batch0.jsonl','evaluation/results/v020-hybrid/translation_batch1.jsonl','evaluation/results/v020-hybrid/translation_batch2.jsonl']:
        files[name]=sha(ROOT/name)
    for p in (ROOT/'evaluation/results/s0-20261013/deps').glob('numpy*'):
        for f in p.rglob('*'):
            if f.is_file() and f.suffix!='.pyc':files[str(f.relative_to(ROOT))]=sha(f)
    manifest=dict(cases=cases,config=CONFIG,max_requests=36,answer_retries=0,batches=[list(range(n,min(n+10,36))) for n in range(0,36,10)],files=files,
        scoring='Known development. Same-case/raw/reference frozen judgments retained; new translations rated on frozen units. Preserved/omitted/contradicted/uncertain, uncertainty not correct. Report30 real-recognized source vs6 human-source diagnostics separately. Old asymmetric willingness rules retained in primary/sensitivity flagged. AI rating not independent human gold.',
        continue_gate='Real-source30 complete meaning +5pp or target errors -20% with net>=3; coverage/overall no drop; new critical error0. Reference-control6 cannot rescue failed product30.',
        resource_gate='load median<=500ms;warm P50<=500ms/P95<=1000ms exploratory; not formal caption E2E',
        normalization='ASCII inputs only, whitespace collapse then sourceSPM then prepend validated language token; model auto sourceEOS; targetSPM decode raw tokens; no output filtering')
    with (OUT/'manifest.json').open('x') as f:json.dump(manifest,f,ensure_ascii=False,indent=2)


def verify():
    active();m=read(OUT/'manifest.json');assert m['config']==CONFIG and len(m['cases'])==m['max_requests']==36
    for p,h in m['files'].items():
        if sha(ROOT/p)!=h:raise RuntimeError('Frozen file changed: '+p)
    return m


def run(batch):
    m=verify();limits=resources()
    if batch not in range(4):raise RuntimeError('Batch invalid')
    path=OUT/f'batch{batch}.jsonl'
    if path.exists():raise RuntimeError('Already started; no implicit retry')
    for n in range(batch):
        rows=list(map(json.loads,(OUT/f'batch{n}.jsonl').read_text().splitlines()))
        if rows[-1]['type']!='engine_closed' or not any(r['type']=='complete' for r in rows):raise RuntimeError('Prior batch incomplete')
    with path.open('x') as f:f.write(json.dumps(dict(type='metadata',manifest_sha256=sha(OUT/'manifest.json'),resources=limits,quota=read(OUT/'quota.json')))+'\n')
    os.environ['OMP_NUM_THREADS']='4';sys.path.insert(0,str(ROOT/'evaluation/results/s0-20261013/deps'));sys.path.insert(0,str(OUT/'deps'))
    import ctranslate2,sentencepiece as spm
    translator=None
    try:
        t=time.monotonic();sp=spm.SentencePieceProcessor(model_file=str(OUT/'original/source.spm'));target=spm.SentencePieceProcessor(model_file=str(OUT/'original/target.spm'))
        translator=ctranslate2.Translator(str(OUT/'ct2-int8'),device='cpu',compute_type='int8',inter_threads=1,intra_threads=4)
        append(path,dict(type='engine_initialized',load_ms=(time.monotonic()-t)*1000))
        for index in m['batches'][batch]:
            active();c=m['cases'][index];tokens=model_input(c['input_text'],sp)
            append(path,dict(type='request_started',index=index,case_id=c['id']))
            t=time.monotonic();result=translator.translate_batch([tokens],beam_size=4,max_decoding_length=128,length_penalty=1.0,return_scores=True)[0]
            raw_tokens=result.hypotheses[0];text=target.decode(raw_tokens)
            append(path,dict(type='request',index=index,case_id=c['id'],input_text=c['input_text'],input_tokens=tokens,output_tokens=raw_tokens,raw=text,score=result.scores[0],decode_ms=(time.monotonic()-t)*1000,possibly_truncated=len(raw_tokens)>=128,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss))
        append(path,dict(type='complete',requests=len(m['batches'][batch]),resources=resources()))
    except BaseException as e:append(path,dict(type='failure',error=repr(e)));raise
    finally:
        t=time.monotonic()
        if translator is not None:translator.unload_model();del translator
        gc.collect();append(path,dict(type='engine_closed',close_ms=(time.monotonic()-t)*1000))


if __name__=='__main__':
    if sys.argv[1]=='prepare':prepare()
    elif sys.argv[1]=='verify':verify()
    elif sys.argv[1]=='run':run(int(sys.argv[2]))
