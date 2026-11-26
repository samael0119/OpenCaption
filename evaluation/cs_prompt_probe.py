"""Two frozen prompt candidates, paired saved inputs; no gold text in prompts."""
import argparse,base64,hashlib,json,shutil,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OLD=ROOT/'evaluation/results/cs-domain-20261020/product_round_v2'
OUT=ROOT/'evaluation/results/cs-prompt-20261021'
JAVA='/home/hyh/Tools/java/eclipse-temurin-jdk17/bin/java'
MODEL=Path('/home/hyh/Tools/litert/models/gemma-4-E2B-it.litertlm')
def read(p):return json.loads(p.read_text())
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
def append(v):
 with (OUT/'screen.jsonl').open('a') as f:f.write(json.dumps(v,ensure_ascii=False)+'\n')
def resources():
 rel=Path('/proc/self/cgroup').read_text().strip().split('::')[1];p=Path('/sys/fs/cgroup')/rel.lstrip('/')
 v={k:(p/k).read_text().strip() for k in ['memory.max','memory.swap.max','memory.peak','memory.events']}
 assert v['memory.max']!='max' and int(v['memory.max'])<=6*1024**3 and v['memory.swap.max']=='0'
 return v
class Bridge:
 def __init__(self,kind):
  cp=(OUT/'classpath.txt').read_text() if kind=='candidate' else (OLD/'classpath.txt').read_text()
  command=['CsPromptProbeBridge'] if kind=='candidate' else ['CsDomainBridge',str(OLD/'names.txt')]
  self.p=subprocess.Popen([JAVA,'-Xmx64m','-cp',cp,*command],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
 def call(self,*fields):
  self.p.stdin.write('\t'.join(fields)+'\n');self.p.stdin.flush();line=self.p.stdout.readline()
  if not line:raise RuntimeError('bridge exited')
  return line.rstrip('\n').split('\t')
 def close(self):
  self.p.stdin.close();assert self.p.wait(timeout=10)==0
enc=lambda s:base64.b64encode(s.encode()).decode()
dec=lambda s:base64.b64decode(s).decode()
def prepare():
 assert not (OUT/'manifest.json').exists()
 OUT.mkdir(exist_ok=True)
 compiler=read(ROOT/'evaluation/results/v020-integrity8/manifest.json')['compiler_files'];cp=list(compiler)
 for p,h in compiler.items():assert sha(p)==h
 classes=OUT/'classes';classes.mkdir()
 source=ROOT/'evaluation/CsPromptCandidates.kt'
 subprocess.run([JAVA,'-Xmx256m','-cp',':'.join(cp),'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler','-no-stdlib','-no-reflect','-jvm-target','17','-classpath',':'.join(cp[1:]),'-d',str(classes),str(source)],check=True)
 runtime=str(classes)+':'+cp[1];(OUT/'classpath.txt').write_text(runtime)
 subprocess.run([str(Path(JAVA).with_name('javac')),'-cp',runtime,'-d',str(classes),str(ROOT/'evaluation/CsPromptProbeBridge.java')],check=True)
 old=[json.loads(x) for x in (OLD/'display.jsonl').read_text().splitlines()]
 picks={'clip':[3,15,23,24],'clip_match_demo2':[3,7,10,12],'clip_match_demo3':[2,5,7,9]}
 cases=[dict(id=f"{r['source_id']}:{r['window']}",group='cs_screen',source_id=r['source_id'],window=r['window'],path=r['path'],sha256=r['sha256'],hints=r['applied_hints'],baseline=dict(english=r['english'],chinese=r['chinese'],display=r['display']['standard']['chinese'])) for r in old if r['arm']=='cs2_auto' and r['window'] in picks.get(r['source_id'],[])]
 prior=read(ROOT/'evaluation/results/accuracy-style-20261019/manifest.json')
 selected=[c for c in prior['cases'] if c['group'] in ['music','known_short_music'] or c['id'] in ['1778','1791','1860']]
 for c in selected:
  cases.append(dict(id='guard:'+c['id'],group='music_guard' if c['group'] in ['music','known_short_music'] else 'speech_guard',path=str(ROOT/c['path']),sha256=sha(ROOT/c['path']),hints='CS2 broadcast.',reference_en=c['reference_en']))
 assert len(cases)==20
 b=Bridge('candidate');prompts={}
 try:
  for v in ['dedup','cs_context']:
   s,p=[dec(x) for x in b.call('prompt',v,enc('CS2 broadcast.'))];prompts[v]=dict(system=s,request_at_start=p)
 finally:b.close()
 files=[source,ROOT/'evaluation/CsPromptProbeBridge.java',ROOT/'evaluation/cs_prompt_probe.py',OLD/'display.jsonl',OLD/'reference.json']+list(classes.rglob('*.class'))
 snap=OUT/'source_snapshot'
 for p in files:
  dest=snap/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
 m=dict(date='2026-10-21',prompts=prompts,cases=cases,screen_calls=40,max_total_new_generation=99,full_followup=59,model_sha256=sha(MODEL),files={str(p):sha(p) for p in files},scope='Development screen selected known CS failures; cached baseline. Same PCM, same applied hints and parser. No roster/answer/future-event injection. Screen raw Chinese; full followup uses actual controller.',decision='One winner chosen after screen: prefer CS candidate if facts/meaning improve without added factual regressions or more than cached1/5 music hallucinations. Full59 closed-loop required before adoption. Reject if no material primary gain.',bounds='single model,CPU4,context768,output128,6GiB,swap0,40 screen calls,no implicit retry')
 (OUT/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n');print('PREPARED40')
def serve():
 m=read(OUT/'manifest.json');assert not (OUT/'screen.jsonl').exists()
 for p,h in m['files'].items():assert sha(p)==h
 assert sha(MODEL)==m['model_sha256'];append(dict(type='metadata',resources=resources(),manifest_sha256=sha(OUT/'manifest.json')))
 import litert_lm as api
 from gemma_replay import response_text
 b=Bridge('candidate');protocol=Bridge('native');model=None
 try:
  model=api.Engine(str(MODEL),backend=api.Backend.CPU(thread_count=4),audio_backend=api.Backend.CPU(thread_count=4),max_num_tokens=768,cache_dir=str(OLD/'cache'),enable_speculative_decoding=None)
  for index,c in enumerate(m['cases']):
   # Alternate order within matched pairs; no prompt revision after outputs.
   variants=['dedup','cs_context'] if index%2==0 else ['cs_context','dedup']
   for v in variants:
    assert sha(c['path'])==c['sha256']
    s,p=[dec(x) for x in b.call('prompt',v,enc(c['hints']))]
    append(dict(type='started',case_id=c['id'],variant=v))
    began=time.monotonic()
    with model.create_conversation(system_message=s,thinking_config=api.ThinkingConfig(False,0),sampler_config=api.SamplerConfig(top_k=1,top_p=1.,temperature=0.),max_output_tokens=128) as cv:
     response=cv.send_message(api.Contents.of(p,api.Content.AudioFile(c['path'])),max_output_tokens=128,thinking_config=api.ThinkingConfig(False,0));raw=response_text(response)
    f=protocol.call('parse',enc(c['hints']),enc(raw));r=dict(type='result',case_id=c['id'],group=c['group'],variant=v,raw=raw,status=f[0],english='',chinese='',inference_ms=(time.monotonic()-began)*1000,raw_tokens=len(model.tokenize(raw)),system_tokens=len(model.tokenize(s)),request_tokens=len(model.tokenize(p)))
    if f[0]=='subtitle':r.update(english=dec(f[1]),chinese=dec(f[2]))
    elif f[0]=='invalid':r['reason']=dec(f[1])
    append(r);print('DONE',index,v,flush=True)
  append(dict(type='complete',requests=40,resources=resources()))
 except BaseException as e:append(dict(type='failure',error=repr(e)));raise
 finally:
  if model:model.close()
  b.close();protocol.close()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','serve']);a=p.parse_args();globals()[a.action]()
