"""R10 single resident model, fixed 12 paired product-prepared inputs."""
import datetime,json,pathlib,subprocess,sys,time,tomllib
from types import SimpleNamespace
from v020_redundancy8 import sha,J,MODEL,Protocol as Previous
R=pathlib.Path(__file__).resolve().parents[1];O=R/'evaluation/results/v020-pcm10';STATE=R/'evaluation/results/v020-continuation/state.json'
def read(p):return json.loads(p.read_text())
def log(x):
 with (O/'requests.jsonl').open('a') as f:f.write(json.dumps(x,ensure_ascii=False)+'\n')
def guard():
 s=read(STATE);a=tomllib.loads(pathlib.Path('/home/hyh/.codex/automations/opencaption/automation.toml').read_text());assert s['status']=='active' and s['current_round']==10 and s['phase'].startswith('round10_') and a['status']=='ACTIVE'
class Protocol(Previous):
 def __init__(self):self.p=subprocess.Popen([J,'-Xmx64m','-cp',(O/'classpath.txt').read_text(),'V020ProtocolBridge'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
def verify():
 guard();m=read(O/'manifest.json')
 for p,h in m['files'].items():assert sha(pathlib.Path(p) if p.startswith('/') else R/p)==h,p
 assert sha(MODEL)==m['model_sha256'];b=Protocol()
 try:assert dict(zip(['system','request'],b.prompt()))==m['prompts']
 finally:b.close()
 return m
def permit(n):
 q=read(O/'permits'/f'{n}.json');assert q['batch']==n and 0<=time.time()-q['at_unix']<180
 assert q['usage_allowed'] and q['weekly_used']<=60 and q['five_hour_used']<100
 if n:assert (O/'permits'/f'{n-1}-after.json').exists()
 return q
def serve():
 m=verify();assert not (O/'requests.jsonl').exists(),'No repeat/retry or model restart'
 from v020_fleurs_pilot import resources
 from gemma_replay import LiteRtRuntime
 limits=resources();permit(0);log(dict(type='metadata',manifest_sha256=sha(O/'manifest.json'),resources=limits));b=Protocol();model=None
 try:
  t=time.monotonic();model=LiteRtRuntime(SimpleNamespace(model=MODEL,threads=4,max_new_tokens=128,hints='',task='bilingual',task_profile='baseline',system_profile='minimal',cache_mode='disk',speculative_decoding='default',max_context_tokens=768));model.system_message=m['prompts']['system'];model.prompt=m['prompts']['request'];log(dict(type='loaded',load_ms=(time.monotonic()-t)*1000));print('READY',flush=True)
  cases={str(c['id']):c for c in m['cases']}
  for batch in range(3):
   command=O/'commands'/str(batch);deadline=time.monotonic()+180
   while not command.exists():
    guard()
    if time.monotonic()>deadline:raise TimeoutError('No fresh command in180s')
    time.sleep(.25)
   assert command.read_text().strip()==f'batch {batch}';guard();permit(batch)
   for item in m['order'][batch*8:(batch+1)*8]:
    guard();c=cases[str(item['case_id'])];path=R/c[item['mode']+'_path'];assert sha(path)==c[item['mode']+'_sha256'];log(dict(type='started',**item,input_sha256=sha(path)));t=time.monotonic();raw=model.infer(path);elapsed=(time.monotonic()-t)*1000;log(dict(type='request',**item,raw=raw,inference_ms=elapsed,input_sha256=sha(path),**b.parse(raw)))
   log(dict(type='batch_complete',batch=batch,done=(batch+1)*8,resources=resources()));print(f'BATCH_COMPLETE {batch}',flush=True)
  log(dict(type='complete',requests=24,resources=resources()));print('COMPLETE24',flush=True)
 except BaseException as e:log(dict(type='failure',error=repr(e)));raise
 finally:
  if model is not None:model.close()
  b.close()
if __name__=='__main__':{'verify':verify,'serve':serve}[sys.argv[1]]()
