"""Round6 final casing candidate. Original manifest and runner stay immutable."""
import gc,json,os,resource,sys,time,tomllib
from pathlib import Path
from v020_mt6_run import ROOT,STATE,AUTO,CONFIG,read,sha,authorized,resources,model_input,append
BASE=ROOT/'evaluation/results/v020-mt6'
OUT=BASE/'casing2'

def lower_input(text):
    if not text.isascii() or not text.isupper():raise ValueError('Only frozen all-uppercase ASCII ASR')
    return text.lower()

def active():
    s=read(STATE)
    authorized(s,tomllib.loads(AUTO.read_text()),read(OUT/'quota.json'),time.time())
    if not s.get('candidate2_budget_approved') or not s.get('execution_switch_confirmed'):raise RuntimeError('Unapproved candidate2')

def prepare():
    active();resources()
    old=read(BASE/'manifest.json');files=dict(old['files'])
    paths=['evaluation/results/v020-mt6/manifest.json','evaluation/v020_mt6_casing.py','evaluation/test_v020_mt6_casing.py','scripts/run-v020-mt6-casing','evaluation/v020_round6_candidate2_review_20261015.md']
    paths += [f'evaluation/results/v020-mt6/batch{n}.jsonl' for n in range(4)]
    for p in paths:files[p]=sha(ROOT/p)
    cases=[]
    for c in old['cases']:
        if c['source_role']!='actual_recognized_text':continue
        c=dict(c);c['original_input_text']=c['input_text'];c['input_text']=lower_input(c['input_text']);cases.append(c)
    assert len(cases)==30
    m=dict(cases=cases,config=CONFIG,max_requests=30,answer_retries=0,batches=[list(range(n,n+10)) for n in range(0,30,10)],files=files,
      unchanged_control_cache_ids=[c['id'] for c in old['cases'] if c['source_role']!='actual_recognized_text'],
      scoring=old['scoring'],continue_gate=old['continue_gate'],resource_gate=old['resource_gate'],
      normalization='Only lower() on all-uppercase ASCII actual ASR. Other pipeline identical. No gold or entity fixes.',
      named_entity_ids=['1272-128104-0001','1272-128104-0014','1272-135031-0005','1272-135031-0008','1272-135031-0011','1272-135031-0013'],acronym_ids=['1272-128104-0014'],
      critical_error_definition='New altered identity/action/negation/number or unsupported factual addition. Spelling/transliteration differences alone not critical. Uncertainty not correct. Separate source fidelity from audio-reference correctness.',
      comparison='cached E2B text + cached MT uppercase + new MT lowercase; original E2B audio separate. Three recovered uppercase regressions are not net repairs vs E2B.',
      semantic_units_unchanged=True,old_willingness_asymmetry_retained=True,AI_assisted_not_independent=True)
    with (OUT/'manifest.json').open('x') as f:json.dump(m,f,ensure_ascii=False,indent=2)

def verify():
    active();m=read(OUT/'manifest.json')
    assert m['config']==CONFIG and len(m['cases'])==m['max_requests']==30 and m['answer_retries']==0
    for p,h in m['files'].items():
        if sha(ROOT/p)!=h:raise RuntimeError('Frozen file changed: '+p)
    for c in m['cases']:
        assert c['input_text']==lower_input(c['original_input_text'])
    return m

def run(batch):
    m=verify();limits=resources()
    if batch not in range(3):raise RuntimeError('Invalid batch')
    path=OUT/f'batch{batch}.jsonl'
    if path.exists():raise RuntimeError('Already started; no retries')
    for n in range(batch):
        rs=[json.loads(x) for x in (OUT/f'batch{n}.jsonl').read_text().splitlines()]
        if rs[-1]['type']!='engine_closed' or not any(r['type']=='complete' for r in rs):raise RuntimeError('Prior batch incomplete')
    with path.open('x') as f:f.write(json.dumps(dict(type='metadata',manifest_sha256=sha(OUT/'manifest.json'),resources=limits,quota=read(OUT/'quota.json')))+'\n')
    os.environ['OMP_NUM_THREADS']='4';sys.path.insert(0,str(ROOT/'evaluation/results/s0-20261013/deps'));sys.path.insert(0,str(BASE/'deps'))
    import ctranslate2,sentencepiece as spm
    translator=None
    try:
        t=time.monotonic();sp=spm.SentencePieceProcessor(model_file=str(BASE/'original/source.spm'));target=spm.SentencePieceProcessor(model_file=str(BASE/'original/target.spm'))
        translator=ctranslate2.Translator(str(BASE/'ct2-int8'),device='cpu',compute_type='int8',inter_threads=1,intra_threads=4)
        append(path,dict(type='engine_initialized',load_ms=(time.monotonic()-t)*1000))
        for index in m['batches'][batch]:
            active();c=m['cases'][index];tokens=model_input(c['input_text'],sp)
            append(path,dict(type='request_started',index=index,case_id=c['id']))
            t=time.monotonic();r=translator.translate_batch([tokens],beam_size=4,max_decoding_length=128,length_penalty=1.0,return_scores=True)[0]
            raw_tokens=r.hypotheses[0];text=target.decode(raw_tokens)
            append(path,dict(type='request',index=index,case_id=c['id'],input_text=c['input_text'],original_input_text=c['original_input_text'],input_tokens=tokens,output_tokens=raw_tokens,raw=text,score=r.scores[0],decode_ms=(time.monotonic()-t)*1000,possibly_truncated=len(raw_tokens)>=128,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss))
        append(path,dict(type='complete',requests=10,resources=resources()))
    except BaseException as e:append(path,dict(type='failure',error=repr(e)));raise
    finally:
        t=time.monotonic()
        if translator is not None:translator.unload_model();del translator
        gc.collect();append(path,dict(type='engine_closed',close_ms=(time.monotonic()-t)*1000))

if __name__=='__main__':
    if sys.argv[1]=='prepare':prepare()
    elif sys.argv[1]=='verify':verify()
    elif sys.argv[1]=='run':run(int(sys.argv[2]))
