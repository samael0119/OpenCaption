"""One contract fix after frozen P0. No new semantic scoring or model calls."""
import collections,json,pathlib,subprocess,sys
import v020_integrity8 as a
B=a.O;C=B/'candidate1';R=a.R

def freeze():
 C.mkdir();old=json.loads((B/'manifest.json').read_text());files=dict(old['files'])
 # Product files changed intentionally; immutable old manifest remains intact.
 for p in ['android/app/src/main/kotlin/dev/opencaption/opencaption/E2eProtocol.kt','android/app/src/test/kotlin/dev/opencaption/opencaption/E2eProtocolTest.kt','evaluation/v020_integrity8_candidate.py','evaluation/results/v020-integrity8/manifest.json','evaluation/results/v020-integrity8/rows.jsonl','evaluation/results/v020-integrity8/mechanism_probes.jsonl']:
  files[p]=a.sha(R/p)
 for p,h in old['files'].items():
  if not p.endswith('/E2eProtocol.kt'):assert a.sha(R/p)==h,p
 cp=dict(old['compiler_files']);cp.update({str(p):a.sha(p) for p in [a.jar('junit','junit','4.13.2'),a.jar('org.hamcrest','hamcrest-core','1.3')]})
 a.O=C;a.write('manifest.json',dict(files=files,compiler_files=cp,rules='Only reject whole cleaned [NONE] mixed reply after all existing pure silence forms. Keep prompt echo stripping and pair selection unchanged. Expected one old subtitle -> invalid, remaining1155 identical, noNoSpeech additions.',new_model_requests=0))
def compile_tests():
 a.O=C;m=a.verify();cp=list(m['compiler_files']);classes=C/'classes';classes.mkdir()
 src=['android/app/src/main/kotlin/dev/opencaption/opencaption/E2eProtocol.kt','android/app/src/main/kotlin/dev/opencaption/opencaption/E2ePreservedNames.kt','android/app/src/test/kotlin/dev/opencaption/opencaption/E2eProtocolTest.kt','evaluation/V020Integrity8.kt']
 cmd=[a.J,'-Xmx256m','-cp',':'.join(cp),'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler','-no-stdlib','-no-reflect','-jvm-target','17','-classpath',':'.join(cp[1:]),'-d',str(classes)]+[str(R/p) for p in src]
 subprocess.run(cmd,check=True);runtime=str(classes)+':'+':'.join(cp[1:]);a.write('compile.json',dict(command=cmd,class_files={str(p.relative_to(C)):a.sha(p) for p in classes.rglob('*.class')},runtime_classpath=runtime))
 subprocess.run([a.J,'-Xmx96m','-cp',runtime,'org.junit.runner.JUnitCore','dev.opencaption.opencaption.E2eProtocolTest'],check=True)
def audit():
 a.O=C;a.verify();b=a.Bridge();changes=[];rows=[];counts=collections.Counter()
 try:
  for l in (B/'rows.jsonl').read_text().splitlines():
   old=json.loads(l);result,cleaned,pairs=b.call(old['task'],old['raw']);counts[result['status']]+=1
   row=dict(source=old['source'],line_no=old['line_no'],raw_sha256=old['raw_sha256'],before=old['current'],after=result)
   rows.append(row)
   if result!=old['current']:changes.append(dict(row,raw=old['raw']))
  assert len(rows)==1156 and len(changes)==1,changes
  assert changes[0]['before']['status']=='subtitle' and changes[0]['after']==dict(status='invalid',english='',chinese='',reason='sentinel_mixed_with_subtitle')
  # Baseline observed probes plus positive/negative assertions on exact contract.
  cases=[('single','English: Go.\nChinese: 去。','subtitle'),('different','English: Go.\nChinese: 去。\nEnglish: Stop.\nChinese: 停。','subtitle'),('duplicate','English: Go.\nChinese: 去。\nEnglish: Go.\nChinese: 去。','subtitle'),('correction','Correction: Previous wrong.\nEnglish: Stop.\nChinese: 停。','subtitle'),('prefix_explanation','Explanation: test\nEnglish: Go.\nChinese: 去。','invalid'),('suffix_note','English: Go.\nChinese: 去。\nNote: extra','subtitle'),('none_prefix','[NONE]\nEnglish: Go.\nChinese: 去。','invalid'),('missing','English: Go.','invalid'),('unknown','French: Go.\nChinese: 去。','subtitle'),('numeric','English: 2\nChinese: 2','subtitle'),('truncated','English: Go.\nChinese:','invalid'),('pure_none','[NONE]\nEnglish: [NONE]\nChinese: [NONE]','no_speech'),('none_between','English: Go.\nChinese: 去。\n[NONE]\nEnglish: Stop.\nChinese: 停。','invalid'),('prompt_echo',a_prompt()+'\nEnglish: Go.\nChinese: 去。','subtitle')]
  probes=[]
  for name,raw,status in cases:
   result,_,_=b.call('bilingual',raw);assert result['status']==status,(name,result);probes.append(dict(name=name,raw=raw,result=result,expected=status))
 finally:b.close()
 for name,data in [('rows.jsonl',rows),('probes.jsonl',probes)]:
  with (C/name).open('x') as f:
   for row in data:f.write(json.dumps(row,ensure_ascii=False)+'\n')
 a.write('summary.json',dict(complete=True,rows=len(rows),unchanged=len(rows)-len(changes),counts=dict(counts),changes=changes,probes_passed=len(probes),new_model_requests=0,protocol_rejection_fix_only=True,content_accuracy_improved=False,coverage_effect='One previously accepted mixed/ambiguous raw becomes explicit invalid gap; correct coverage unknown.',independent_acceptance=False))
 print((C/'summary.json').read_text())
def a_prompt():
 # Frozen baseline product constant, extracted verbatim from old successful prompt probe by bridge-independent source expression is avoided.
 # Read source constant string literals; only the specific PROMPT declaration.
 import re
 s=(R/'android/app/src/main/kotlin/dev/opencaption/opencaption/E2eProtocol.kt').read_text().split('const val PROMPT =',1)[1].split('sealed interface',1)[0]
 return ''.join(json.loads(x) for x in re.findall(r'"(?:[^"\\]|\\.)*"',s))
if __name__=='__main__':{'freeze':freeze,'compile':compile_tests,'audit':audit}[sys.argv[1]]()
