"""One explicit revision after initial screen: split roles + curated spelling data."""
import argparse,json,shutil,subprocess,time
from pathlib import Path
import cs_prompt_probe as probe
ROOT=probe.ROOT;OUT=probe.OUT/'compact';JAVA=probe.JAVA;MODEL=probe.MODEL
read=probe.read;sha=probe.sha;enc=probe.enc;dec=probe.dec
class CompactBridge:
 def __init__(self):
  self.p=subprocess.Popen([JAVA,'-Xmx64m','-cp',(OUT/'classpath.txt').read_text(),'CsPromptCompactBridge'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
 def call(self,*fields):
  self.p.stdin.write(fields[-1]+'\n');self.p.stdin.flush();line=self.p.stdout.readline()
  if not line:raise RuntimeError('compact bridge exited')
  return line.rstrip('\n').split('\t')
 def close(self):self.p.stdin.close();assert self.p.wait(timeout=10)==0

def append(v):
 with (OUT/'screen.jsonl').open('a') as f:f.write(json.dumps(v,ensure_ascii=False)+'\n')
def prepare():
 assert not (OUT/'manifest.json').exists()
 m=read(probe.OUT/'manifest.json');hint={r['id']:r['hints'] for r in read(OUT/'hints_input.json.out')}
 for c in m['cases']:c['hints']=hint[c['id']]
 cp=list(read(ROOT/'evaluation/results/v020-integrity8/manifest.json')['compiler_files']);classes=OUT/'classes';classes.mkdir()
 source=ROOT/'evaluation/CsPromptCompact.kt'
 subprocess.run([JAVA,'-Xmx256m','-cp',':'.join(cp),'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler','-no-stdlib','-no-reflect','-jvm-target','17','-classpath',':'.join(cp[1:]),'-d',str(classes),str(source)],check=True)
 runtime=str(classes)+':'+cp[1];(OUT/'classpath.txt').write_text(runtime)
 subprocess.run([str(Path(JAVA).with_name('javac')),'-cp',runtime,'-d',str(classes),str(ROOT/'evaluation/CsPromptCompactBridge.java')],check=True)
 b=CompactBridge()
 try:s,p=[dec(x) for x in b.call(enc('CS2 broadcast.'))]
 finally:b.close()
 files=[source,ROOT/'evaluation/CsPromptCompactBridge.java',ROOT/'evaluation/cs_prompt_compact.py',OUT/'hints_input.json.out']+list(classes.rglob('*.class'))
 snapshot=OUT/'source_snapshot'
 for pth in files:
  dest=snapshot/pth.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(pth,dest)
 m.update(variant='cs_compact',screen_calls=20,total_new_generation_bound=119,prompt=dict(system=s,user_at_empty=p),files={str(p):sha(p) for p in files},spelling_data_provenance='Frozen hints_input.json.out from archived real Dart formatter; rejected formatter is not a production default',revision_reason='Initial long system-only CS prompt had literal template tags and weak semantics; explicit new version splits task into user and adds existing curated spelling aliases, not a roster. Both changed factors reported together; no per-factor causal claim.')
 (OUT/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n');print('PREPARED20')
def serve():
 m=read(OUT/'manifest.json');assert not (OUT/'screen.jsonl').exists()
 for p,h in m['files'].items():assert sha(p)==h
 assert sha(MODEL)==m['model_sha256'];append(dict(type='metadata',resources=probe.resources()))
 import litert_lm as api
 from gemma_replay import response_text
 b=CompactBridge();native=probe.Bridge('native');model=None
 try:
  model=api.Engine(str(MODEL),backend=api.Backend.CPU(thread_count=4),audio_backend=api.Backend.CPU(thread_count=4),max_num_tokens=768,cache_dir=str(probe.OLD/'cache'),enable_speculative_decoding=None)
  for i,c in enumerate(m['cases']):
   assert sha(c['path'])==c['sha256'];s,p=[dec(x) for x in b.call(enc(c['hints']))]
   append(dict(type='started',case_id=c['id']))
   began=time.monotonic()
   with model.create_conversation(system_message=s,thinking_config=api.ThinkingConfig(False,0),sampler_config=api.SamplerConfig(top_k=1,top_p=1.,temperature=0.),max_output_tokens=128) as cv:
    raw=response_text(cv.send_message(api.Contents.of(p,api.Content.AudioFile(c['path'])),max_output_tokens=128,thinking_config=api.ThinkingConfig(False,0)))
   f=native.call('parse',enc(c['hints']),enc(raw));r=dict(type='result',case_id=c['id'],group=c['group'],variant=m.get('variant','cs_compact'),raw=raw,status=f[0],english='',chinese='',inference_ms=(time.monotonic()-began)*1000,raw_tokens=len(model.tokenize(raw)),system_tokens=len(model.tokenize(s)),request_tokens=len(model.tokenize(p)))
   if f[0]=='subtitle':r.update(english=dec(f[1]),chinese=dec(f[2]))
   elif f[0]=='invalid':r['reason']=dec(f[1])
   append(r);print('DONE',i,flush=True)
  append(dict(type='complete',requests=len(m['cases']),resources=probe.resources()))
 except BaseException as e:append(dict(type='failure',error=repr(e)));raise
 finally:
  if model:model.close()
  b.close();native.close()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','serve']);a=p.parse_args();globals()[a.action]()
