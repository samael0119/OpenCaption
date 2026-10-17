"""Single-residency, quota-permitted <=10-call batches for one fixed prompt."""
import base64,datetime,hashlib,json,pathlib,resource,subprocess,sys,time,tomllib
from types import SimpleNamespace
R=pathlib.Path(__file__).resolve().parents[1];O=R/'evaluation/results/v020-redundancy8';STATE=R/'evaluation/results/v020-continuation/state.json'
MODEL=pathlib.Path('/home/hyh/Tools/litert/models/gemma-4-E2B-it.litertlm')
ADD='Begin immediately with English: or [NONE]. Do not write an unlabeled transcription before the labeled English and Chinese lines. Do not repeat either line.'
J='/home/hyh/Tools/java/eclipse-temurin-jdk17/bin/java'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for x in iter(lambda:f.read(1048576),b''):h.update(x)
 return h.hexdigest()
def read(p):return json.loads(p.read_text())
def put(p,d):
 with p.open('x') as f:json.dump(d,f,ensure_ascii=False,indent=2)
def append(p,d):
 with p.open('a') as f:f.write(json.dumps(d,ensure_ascii=False)+'\n')
def guard():
 s=read(STATE);a=tomllib.loads(pathlib.Path('/home/hyh/.codex/automations/opencaption/automation.toml').read_text())
 if s['status']!='active' or a['status']!='ACTIVE' or s['current_round']!=8 or not s['phase'].startswith('round8_redundancy_'):raise RuntimeError('Not authorized round8')
def verify():
 guard();m=read(O/'manifest.json')
 for p,h in m['files'].items():
  if sha(pathlib.Path(p) if p.startswith('/') else R/p)!=h:raise RuntimeError('Changed dependency '+p)
 return m
class Protocol:
 def __init__(self):
  self.p=subprocess.Popen([J,'-Xmx64m','-cp',(O/'classpath.txt').read_text(),'V020ProtocolBridge'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
 def send(self,cmd,task,value):
  self.p.stdin.write(cmd+'\t'+task+'\t'+base64.b64encode(value.encode()).decode()+'\n');self.p.stdin.flush();f=self.p.stdout.readline().rstrip('\r\n').split('\t');return f
 def prompt(self):return [base64.b64decode(v).decode() for v in self.send('prompt','bilingual','CS2 broadcast.')]
 def parse(self,raw):
  f=self.send('parse','bilingual',raw);d=dict(status=f[0],english='',chinese='',reason='')
  if f[0]=='subtitle':d.update(english=base64.b64decode(f[1]).decode(),chinese=base64.b64decode(f[2]).decode())
  elif f[0]=='invalid':d['reason']=base64.b64decode(f[1]).decode()
  elif f[0]!='no_speech':raise RuntimeError('Bridge failed')
  return d
 def close(self):self.p.stdin.close();assert self.p.wait(timeout=10)==0

def prepare():
 guard();p0=read(O/'P0_manifest.json');assert read(O/'P0_summary.json')['development41']['repeated']>0
 for p,h in p0['files'].items():assert sha(R/p)==h,p
 im=read(R/'evaluation/results/v020-integrity8/manifest.json');cp=list(im['compiler_files']);classes=O/'classes';classes.mkdir()
 for p,h in im['compiler_files'].items():assert sha(pathlib.Path(p))==h
 src=['android/app/src/main/kotlin/dev/opencaption/opencaption/E2eProtocol.kt','android/app/src/main/kotlin/dev/opencaption/opencaption/E2ePreservedNames.kt']
 cmd=[J,'-Xmx256m','-cp',':'.join(cp),'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler','-no-stdlib','-no-reflect','-jvm-target','17','-classpath',':'.join(cp[1:]),'-d',str(classes)]+[str(R/p) for p in src];subprocess.run(cmd,check=True)
 runtime=str(classes)+':'+cp[1];subprocess.run([str(pathlib.Path(J).with_name('javac')),'-cp',runtime,'-d',str(classes),str(R/'evaluation/V020ProtocolBridge.java')],check=True)
 (O/'classpath.txt').write_text(runtime)
 b=Protocol()
 try:system,request=b.prompt()
 finally:b.close()
 assert dict(system=system,request=request)==p0['prompts']
 order=[];idx={}
 for c in p0['cases']:
  g=c['group'];i=idx.get(g,0);idx[g]=i+1
  for mode in (['baseline','candidate'] if i%2==0 else ['candidate','baseline']):order.append(dict(index=len(order),case_id=c['id'],group=g,mode=mode))
 assert len(order)==82
 files=dict(p0['files']);files.update({p:sha(R/p) for p in src+['evaluation/v020_redundancy8.py','evaluation/gemma_replay.py','evaluation/score_reference.py','evaluation/v020_semantic_rating_cache.py','evaluation/V020ProtocolBridge.java','scripts/run-v020-redundancy8']})
 for d in ['evaluation/results/v020-round2/scene-denial/source_snapshot.json','evaluation/results/v020-convergence/g1_semantic_review.json','evaluation/results/v020-round2/noise1/semantic_review_consistent.json','evaluation/results/v020-convergence/gain1_semantic_review.json']:
  files[d]=sha(R/d)
 for p in classes.rglob('*.class'):files[str(p.relative_to(R))]=sha(p)
 files['evaluation/results/v020-redundancy8/classpath.txt']=sha(O/'classpath.txt');files.update(im['compiler_files'])
 import litert_lm
 package=pathlib.Path(litert_lm.__file__).parent
 for p in package.rglob('*.py'):files[str(p)]=sha(p)
 # Model hashing is streamed; no Engine or native model allocation here.
 assert sha(MODEL)==p0['model_sha256']
 m=dict(cases=p0['cases'],order=order,files=files,prompts=dict(system=system,baseline=request,candidate=request+'\n'+ADD),config=p0['config'],model_sha256=p0['model_sha256'],bounds=dict(max_requests=82,retries=0,model_residencies=1,batch_max=10,memory=6*1024**3,swap=0,timeout=1800),scoring=p0['score_policy'],rating_note='Reuse exact case/raw/ref frozen ratings, otherwise explicit AI-assisted review; no independent gold or E2E claim.',gates=dict(redundant_fraction_reduction=.8,median_decode_improvement=.2,p95_regression_max=.05,new_critical_errors=0,coverage_nonregression=True),sdk_version=getattr(litert_lm,'__version__','unknown'),new_calls_at_freeze=0)
 put(O/'manifest.json',m);put(O/'compile.json',dict(command=cmd,class_files={str(p.relative_to(R)):sha(p) for p in classes.rglob('*.class')}));print('FROZEN 41pairs/82max; zero model initialization',flush=True)

def permit(n):
 p=read(O/'permits'/f'{n}.json');assert p['batch']==n and time.time()-p['at_unix']<180
 assert p['weekly_used']<=60 and p['usage_allowed'] and p['five_hour_used']<100
 if n:assert (O/'permits'/f'{n-1}-after.json').exists()
 return p

def serve():
 m=verify();assert not (O/'requests.jsonl').exists(),'No retry/residency restart'
 from v020_fleurs_pilot import resources
 from gemma_replay import LiteRtRuntime
 limits=resources();permit(0);assert sha(MODEL)==m['model_sha256']
 append(O/'requests.jsonl',dict(type='metadata',manifest_sha256=sha(O/'manifest.json'),resources=limits,at=datetime.datetime.now().astimezone().isoformat(),model_residencies=1))
 b=Protocol();model=None
 try:
  began=time.monotonic();model=LiteRtRuntime(SimpleNamespace(model=MODEL,threads=4,max_new_tokens=128,hints='',task='bilingual',task_profile='baseline',system_profile='minimal',cache_mode='disk',speculative_decoding='default',max_context_tokens=768))
  append(O/'requests.jsonl',dict(type='loaded',load_ms=(time.monotonic()-began)*1000,resources=resources()));print('READY',flush=True)
  done=0;batch=0;cases={str(c['id']):c for c in m['cases']}
  for line in sys.stdin:
   if line.strip()=='stop':break
   if line.strip()!=f'batch {batch}':raise RuntimeError('Unexpected batch; no repeats')
   guard();quota=permit(batch);end=min(done+10,82)
   for item in m['order'][done:end]:
    guard();c=cases[str(item['case_id'])]
    append(O/'requests.jsonl',dict(type='started',**item,input_sha256=c['sha256']))
    model.system_message=m['prompts']['system'];model.prompt=m['prompts'][item['mode']]
    start=time.monotonic();raw=model.infer(R/c['path']);ms=(time.monotonic()-start)*1000;parsed=b.parse(raw)
    append(O/'requests.jsonl',dict(type='request',**item,raw=raw,inference_ms=ms,input_sha256=c['sha256'],**parsed,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss));done+=1
   append(O/'requests.jsonl',dict(type='batch_complete',batch=batch,done=done,resources=resources()));print(f'BATCH_COMPLETE {batch} done={done}',flush=True);batch+=1
   if done==82:
    append(O/'requests.jsonl',dict(type='complete',requests=done,resources=resources()));print('COMPLETE82',flush=True);break
 except BaseException as e:
  append(O/'requests.jsonl',dict(type='failure',error=repr(e)));raise
 finally:
  if model is not None:model.close()
  b.close()
if __name__=='__main__':{'prepare':prepare,'serve':serve,'verify':verify}[sys.argv[1]]()
