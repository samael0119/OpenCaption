"""Final rules-only candidate: eight guards, then separate full59 controller run."""
import argparse,json,shutil,subprocess
from pathlib import Path
import cs_prompt_probe as probe
import cs_prompt_compact as engine
ROOT=probe.ROOT;OUT=probe.OUT/'final_guards';JAVA=probe.JAVA
class FinalBridge:
 def __init__(self):
  self.p=subprocess.Popen([JAVA,'-Xmx64m','-cp',(OUT/'classpath.txt').read_text(),'CsPromptFinalBridge'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
 def call(self,*f):
  self.p.stdin.write(f[-1]+'\n');self.p.stdin.flush();line=self.p.stdout.readline()
  if not line:raise RuntimeError('final prompt bridge exited')
  return line.rstrip('\n').split('\t')
 def close(self):self.p.stdin.close();assert self.p.wait(timeout=10)==0
def prepare():
 assert not (OUT/'manifest.json').exists();OUT.mkdir()
 cp=list(probe.read(ROOT/'evaluation/results/v020-integrity8/manifest.json')['compiler_files']);classes=OUT/'classes';classes.mkdir()
 source=ROOT/'evaluation/CsPromptFinal.kt'
 subprocess.run([JAVA,'-Xmx256m','-cp',':'.join(cp),'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler','-no-stdlib','-no-reflect','-jvm-target','17','-classpath',':'.join(cp[1:]),'-d',str(classes),str(source)],check=True)
 runtime=str(classes)+':'+cp[1];(OUT/'classpath.txt').write_text(runtime)
 subprocess.run([str(Path(JAVA).with_name('javac')),'-cp',runtime,'-d',str(classes),str(ROOT/'evaluation/CsPromptFinalBridge.java')],check=True)
 m=probe.read(probe.OUT/'manifest.json');m['cases']=[c for c in m['cases'] if c['group']!='cs_screen'];assert len(m['cases'])==8
 b=FinalBridge()
 try:s,p=[probe.dec(v) for v in b.call(probe.enc('CS2 broadcast.'))]
 finally:b.close()
 files=[source,ROOT/'evaluation/CsPromptFinalBridge.java',ROOT/'evaluation/cs_prompt_final.py',ROOT/'evaluation/cs_prompt_compact.py']+list(classes.rglob('*.class'))
 for f in files:
  t=OUT/'source_snapshot'/f.relative_to(ROOT);t.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(f,t)
 m.update(variant='cs_rules',screen_calls=8,total_new_generation_bound=127,prompt=dict(system=s,user_at_empty=p),files={str(f):probe.sha(f) for f in files},scope='Last version, rules only and original actual context, no added global ID aliases. Same five music and three ordinary-speech guards. Up to59 full; maximum127 total, no further prompt variants.')
 (OUT/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n');print('PREPARED8')
def serve():
 engine.OUT=OUT;engine.CompactBridge=FinalBridge;engine.serve()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','serve']);a=p.parse_args();globals()[a.action]()
