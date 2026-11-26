"""One frozen winner through the real Dart closed loop; reuses exact prior PCM."""
import argparse,json,shutil
from pathlib import Path
import cs_domain_round as core
import cs_prompt_probe as probe
import cs_prompt_compact as compact
import cs_prompt_final as final
ROOT=core.ROOT
OUT=probe.OUT/'full'
NativeBridge=core.Bridge
class FullBridge:
 def __init__(self):
  self.native=NativeBridge();self.variant=core.read(OUT/'manifest.json')['candidate']
  self.candidate=(final.FinalBridge() if self.variant=='cs_rules' else compact.CompactBridge() if self.variant=='cs_compact' else probe.Bridge('candidate'))
 def call(self,*f):
  if f[0]=='prompt':return self.candidate.call('prompt',self.variant,f[1])
  return self.native.call(*f)
 def close(self):self.candidate.close();self.native.close()
def prepare(variant):
 assert variant in ['dedup','cs_context','cs_compact','cs_rules'] and not (OUT/'manifest.json').exists()
 OUT.mkdir(exist_ok=True)
 for name in ['commands','responses']:(OUT/name).mkdir()
 m=core.read(probe.OLD/'manifest.json');m.update(candidate=variant,arms=['cs2_auto'],request_budget=59,screen_manifest_sha256=core.sha(probe.OUT/'manifest.json'),scope='Fresh prompt winner + actual Dart corpus/controller; prior fixed-fallback PCM, development reference only; no VAD/queue/phone')
 files=[ROOT/'evaluation/cs_prompt_full.py',ROOT/'evaluation/cs_domain_round.py',ROOT/'evaluation/cs_prompt_probe.py',ROOT/'evaluation/CsPromptCandidates.kt',ROOT/'test/cs_domain_live_eval_test.dart',probe.OUT/'manifest.json']+list((ROOT/'lib/core').glob('*.dart'))+list((ROOT/'assets/corpora').rglob('*.json'))
 files+=list((probe.OUT/'classes').rglob('*.class'))+list((probe.OLD/'classes').rglob('*.class'))
 if variant=='cs_compact':
  files += [ROOT/'evaluation/cs_prompt_compact.py',ROOT/'evaluation/CsPromptCompact.kt',compact.OUT/'manifest.json']+list((compact.OUT/'classes').rglob('*.class'))
 if variant=='cs_rules':
  files += [ROOT/'evaluation/cs_prompt_final.py',ROOT/'evaluation/cs_prompt_compact.py',ROOT/'evaluation/CsPromptFinal.kt',final.OUT/'manifest.json']+list((final.OUT/'classes').rglob('*.class'))
 m['files']={str(p):core.sha(p) for p in files}
 snapshot=OUT/'source_snapshot'
 for p in files:
  dest=snapshot/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
 shutil.copyfile(probe.OLD/'reference.json',OUT/'reference.json');shutil.copyfile(probe.OLD/'classpath.txt',OUT/'classpath.txt')
 (OUT/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
 print('PREPARED59',variant)
def serve():
 core.OUT=OUT;core.Bridge=FullBridge;core.serve()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','serve']);p.add_argument('--variant',choices=['dedup','cs_context','cs_compact','cs_rules']);a=p.parse_args()
 prepare(a.variant) if a.action=='prepare' else serve()
