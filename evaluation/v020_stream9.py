"""R9 bounded synchronous/stream timing; no provisional product delivery."""
import base64,collections,datetime,hashlib,json,pathlib,re,subprocess,sys,time,tomllib
from types import SimpleNamespace
from v020_redundancy8 import sha,Protocol as OldProtocol,J,MODEL
R=pathlib.Path(__file__).resolve().parents[1];O=R/'evaluation/results/v020-stream9';STATE=R/'evaluation/results/v020-continuation/state.json'
def read(p):return json.loads(p.read_text())
def put(p,x):
 with p.open('x') as f:json.dump(x,f,ensure_ascii=False,indent=2)
def log(x):
 with (O/'requests.jsonl').open('a') as f:f.write(json.dumps(x,ensure_ascii=False)+'\n')
def guard():
 s=read(STATE);a=tomllib.loads(pathlib.Path('/home/hyh/.codex/automations/opencaption/automation.toml').read_text())
 assert s['status']=='active' and s['current_round']==9 and s['phase'].startswith('round9_') and a['status']=='ACTIVE'
class Protocol(OldProtocol):
 def __init__(self):self.p=subprocess.Popen([J,'-Xmx64m','-cp',(O/'classpath.txt').read_text(),'V020ProtocolBridge'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
def text_chunk(msg):
 # Only the SDK's documented text content shape is accepted; unknown blocks fail.
 if not isinstance(msg,dict) or msg.get('role','assistant')!='assistant':raise ValueError('Unknown message')
 c=msg.get('content',[])
 if isinstance(c,str):return c
 if isinstance(c,dict):c=[c]
 if not isinstance(c,list):raise ValueError('Unknown content')
 out=[]
 for b in c:
  if not isinstance(b,dict) or b.get('type')!='text' or not isinstance(b.get('text'),str):raise ValueError('Unknown nontext block')
  out.append(b['text'])
 return ''.join(out)
def reconstructions(chunks):
 # Keep both hypotheses until paired sync evidence disambiguates native chunks.
 texts=[text_chunk(x) for x in chunks];nonempty=[t for t in texts if t]
 return dict(delta=''.join(texts),cumulative=nonempty[-1] if nonempty else '',cumulative_monotonic=all(b.startswith(a) for a,b in zip(nonempty,nonempty[1:])))
def permit(n):
 q=read(O/'permits'/f'{n}.json');assert q['batch']==n and 0<=time.time()-q['at_unix']<180
 assert q['usage_allowed'] and q['weekly_used']<=60 and q['five_hour_used']<100
 if n:assert (O/'permits'/f'{n-1}-after.json').exists()
 return q
def prepare():
 guard();O.mkdir(exist_ok=True);assert not (O/'manifest.json').exists()
 old=read(R/'evaluation/results/v020-redundancy8/P0_manifest.json');source=R/'evaluation/results/v020-integrity8/rows.jsonl';rows=[json.loads(l) for l in source.read_text().splitlines()]
 baseline=[c['old_cached_structure'] for c in old['cases']]
 def stats(rs):
  out=[]
  for x in rs:
   p=x.get('pairs',[]);raw=x['raw'];zh=p[-1]['chinese'] if p else '';pos=raw.rfind(zh) if zh else -1
   out.append(dict(raw_sha256=hashlib.sha256(raw.encode()).hexdigest(),has_chinese=bool(zh),chinese_start=pos if pos>=0 else None,chinese_characters=len(zh),first_sentence_end=next((i+1 for i,c in enumerate(zh) if c in '。！？!?'),None),characters_after_final_chinese=len(raw)-(pos+len(zh)) if pos>=0 else None))
  return dict(rows=len(rs),with_chinese=sum(x['has_chinese'] for x in out),items=out,char_metrics_not_timing=True)
 put(O/'P0_summary.json',dict(all1156=stats(rows),unique_raw=stats(list({x['raw_sha256']:x for x in rows}.values())),development41=stats(baseline),new_model_requests=0))
 groups=['fleurs_semantic','natural_whisper','ordinary','music','known_short_music'];cases=[]
 for g,n in zip(groups,[2,2,2,1,1]):cases += [c for c in old['cases'] if c['group']==g][:n]
 assert len(cases)==8
 order=[]
 for i,c in enumerate(cases):
  for mode in (['sync','stream'] if i%2==0 else ['stream','sync']):order.append(dict(index=len(order),case_id=c['id'],group=c['group'],mode=mode))
 im=read(R/'evaluation/results/v020-integrity8/manifest.json');cp=list(im['compiler_files']);classes=O/'classes';classes.mkdir()
 for p,h in im['compiler_files'].items():assert sha(pathlib.Path(p))==h
 src=['android/app/src/main/kotlin/dev/opencaption/opencaption/E2eProtocol.kt','android/app/src/main/kotlin/dev/opencaption/opencaption/E2ePreservedNames.kt']
 cmd=[J,'-Xmx256m','-cp',':'.join(cp),'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler','-no-stdlib','-no-reflect','-jvm-target','17','-classpath',':'.join(cp[1:]),'-d',str(classes)]+[str(R/p) for p in src];subprocess.run(cmd,check=True)
 runtime=str(classes)+':'+cp[1];subprocess.run([str(pathlib.Path(J).with_name('javac')),'-cp',runtime,'-d',str(classes),str(R/'evaluation/V020ProtocolBridge.java')],check=True);(O/'classpath.txt').write_text(runtime)
 b=Protocol()
 try:system,request=b.prompt()
 finally:b.close()
 assert dict(system=system,request=request)==old['prompts']
 import litert_lm
 files={str(p):sha(p) for p in pathlib.Path(litert_lm.__file__).parent.rglob('*.py')};files.update(im['compiler_files'])
 paths=src+['evaluation/gemma_replay.py','evaluation/v020_redundancy8.py','evaluation/v020_stream9.py','evaluation/test_v020_stream9.py','evaluation/V020ProtocolBridge.java','scripts/run-v020-stream9','docs/dev/archive/v0.2.0第9轮流式交付归因计划.md','evaluation/results/v020-redundancy8/P0_manifest.json',str(source.relative_to(R))]+[c['path'] for c in cases]
 files.update({p:sha(R/p) for p in paths});files.update({str(p.relative_to(R)):sha(p) for p in classes.rglob('*.class')});files[str((O/'classpath.txt').relative_to(R))]=sha(O/'classpath.txt')
 assert sha(MODEL)==old['model_sha256']
 put(O/'manifest.json',dict(cases=cases,order=order,files=files,model_sha256=old['model_sha256'],prompts=dict(system=system,request=request),bounds=dict(requests=16,batches=[8,8],retries=0,residencies=1,memory=6*1024**3,swap=0,timeout=900),config=old['config'],stream_semantics='Both delta/cumulative hypotheses retained until paired output evidence; ambiguous mismatch cannot pass',sdk_version=getattr(litert_lm,'__version__','unknown'),new_requests_at_freeze=0));put(O/'compile.json',dict(command=cmd));print('FROZEN8pairs/16requests; zero Engine',flush=True)
def verify():
 guard();m=read(O/'manifest.json')
 for p,h in m['files'].items():assert sha(pathlib.Path(p) if p.startswith('/') else R/p)==h,p
 assert sha(MODEL)==m['model_sha256'];return m
def serve():
 m=verify();assert not (O/'requests.jsonl').exists(),'No implicit residency restart/retry'
 from v020_fleurs_pilot import resources
 from gemma_replay import LiteRtRuntime,response_text
 resources();permit(0);b=Protocol();model=None;log(dict(type='metadata',resources=resources(),manifest_sha256=sha(O/'manifest.json')))
 try:
  t=time.monotonic();model=LiteRtRuntime(SimpleNamespace(model=MODEL,threads=4,max_new_tokens=128,hints='',task='bilingual',task_profile='baseline',system_profile='minimal',cache_mode='disk',speculative_decoding='default',max_context_tokens=768));log(dict(type='loaded',load_ms=(time.monotonic()-t)*1000));print('READY',flush=True)
  cases={str(c['id']):c for c in m['cases']};api=model.api
  for batch in range(2):
   command=O/'commands'/str(batch);deadline=time.monotonic()+180
   while not command.exists():
    guard()
    if time.monotonic()>deadline:raise TimeoutError('No command in180s')
    time.sleep(.25)
   assert command.read_text().strip()==f'batch {batch}';guard();permit(batch)
   for item in m['order'][batch*8:(batch+1)*8]:
    guard();c=cases[str(item['case_id'])];log(dict(type='started',**item));t=time.monotonic();chunks=[];events=[]
    with model.engine.create_conversation(system_message=m['prompts']['system'],thinking_config=api.ThinkingConfig(False,0),sampler_config=api.SamplerConfig(top_k=1,top_p=1.0,temperature=0.0),max_output_tokens=128) as conv:
     msg=api.Contents.of(m['prompts']['request'],api.Content.AudioFile(str((R/c['path']).resolve())));gen=time.monotonic()
     if item['mode']=='sync':
      response=conv.send_message(msg,max_output_tokens=128,thinking_config=api.ThinkingConfig(False,0));raw=response_text(response);log(dict(type='sync_response',**item,response=response,at_ms=(time.monotonic()-t)*1000))
     else:
      # Preserve raw callback messages before validating; unknown shape never discarded.
      for chunk in conv.send_message_async(msg,max_output_tokens=128,thinking_config=api.ThinkingConfig(False,0)):
       at=(time.monotonic()-t)*1000;log(dict(type='chunk',**item,chunk=chunk,at_ms=at));text_chunk(chunk);chunks.append(chunk);events.append(at)
      raw=None
     generation_ms=(time.monotonic()-gen)*1000;stream_end_ms=(time.monotonic()-t)*1000
    elapsed=(time.monotonic()-t)*1000
    record=dict(type='request',**item,service_ms=elapsed,generation_ms=generation_ms,stream_end_ms=stream_end_ms,input_sha256=c['sha256'])
    if raw is not None:record.update(raw=raw,parsed=b.parse(raw))
    else:record.update(hypotheses=reconstructions(chunks),chunk_times_ms=events,chunk_count=len(chunks),note='Iterator exhaustion observed; private final C bit not exposed by public API')
    log(record)
   log(dict(type='batch_complete',batch=batch,done=(batch+1)*8,resources=resources()));print(f'BATCH_COMPLETE {batch}',flush=True)
  log(dict(type='complete',requests=16,resources=resources()));print('COMPLETE16',flush=True)
 except BaseException as e:log(dict(type='failure',error=repr(e)));raise
 finally:
  if model is not None:model.close()
  b.close()
if __name__=='__main__':{'prepare':prepare,'verify':verify,'serve':serve}[sys.argv[1]]()
