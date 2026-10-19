"""R11 sixteen-call diagnostic. Human source text never enters audio arm."""
import array,json,pathlib,subprocess,sys,time,tomllib
from types import SimpleNamespace
from v020_redundancy8 import R,J,MODEL,sha,Protocol as Parent
from v020_pcm10_prepare import extract
from v020_convergence_g1 import TEXT_SYSTEM,text_infer
O=R/'evaluation/results/v020-diagnostic11'
STATE=R/'evaluation/results/v020-continuation/state.json'
def read(p):return json.loads(p.read_text())
def put(n,x):(O/n).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def log(x):
 with (O/'requests.jsonl').open('a') as f:f.write(json.dumps(x,ensure_ascii=False)+'\n')
def guard():
 s=read(STATE);a=tomllib.loads(pathlib.Path('/home/hyh/.codex/automations/opencaption/automation.toml').read_text())
 assert s['status']=='active' and s['current_round']==11 and s['phase'].startswith('round11_P1_') and s['round11_request_budget']['P1']==16 and a['status']=='ACTIVE'
class Protocol(Parent):
 def __init__(self):self.p=subprocess.Popen([J,'-Xmx64m','-cp',(O/'classpath.txt').read_text(),'V020ProtocolBridge'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
def permit(n):
 q=read(O/'permits'/f'{n}.json');assert q['batch']==n and 0<=time.time()-q['at_unix']<180 and q['usage_allowed'] and q['weekly_used']<=60 and q['five_hour_used']<100
 if n:assert (O/'permits'/f'{n-1}-after.json').exists()
 return q
UNITS={
1860:['Governor office attributed the statement','injured subset were police officers','number nineteen'],
1870:['scenes shown on pyramids','different pyramids illuminated'],
1889:['it brought us train and car','many other transportation devices'],
1908:['important distinguishing method','some verbs contrasted with objects; isolated objects sense uncertain'],
1941:['these couples as agents','may choose, not certain action','adoption plan concerning their baby; direction unspecified'],
1957:['he attributed description to rumors','political chatter description','silliness description'],
1972:['many people do not regard them as dinosaurs','because they have feathers','because they can fly'],
1978:['Springboks as affected team','five-match losing streak','streak ended, not finishing with losses']}
def prepare():
 guard();O.mkdir(exist_ok=True);assert not (O/'manifest.json').exists()
 backend=R/'android/app/src/gemmaE2E/kotlin/dev/opencaption/opencaption/FlavorBackendFactory.kt'
 capture=R/'android/app/src/main/kotlin/dev/opencaption/opencaption/CaptionEngine.kt'
 assert 'val floats = FloatArray(count) { pcm[it] / 32768f }' in capture.read_text()
 method=extract(backend.read_text(),'private fun wav(samples: FloatArray): ByteArray')
 assert '(it.coerceIn(-1f, 1f) * 32767).toInt().toShort()' in method
 source='''import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.io.File
import dev.opencaption.opencaption.E2eAudioInput
object V020Diagnostic11Input {
'''+method+'''
@JvmStatic fun main(args:Array<String>){
val bytes=File(args[0]).readBytes();check(bytes.size%2==0)
val buf=ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
val x=FloatArray(bytes.size/2){buf.short/32768f}
File(args[1]).writeBytes(wav(E2eAudioInput.prepareShort(x)))
}}
'''
 (O/'V020Diagnostic11Input.kt').write_text(source)
 im=read(R/'evaluation/results/v020-integrity8/manifest.json');cp=list(im['compiler_files'])
 for p,h in im['compiler_files'].items():assert sha(pathlib.Path(p))==h
 classes=O/'classes';classes.mkdir()
 src=['android/app/src/main/kotlin/dev/opencaption/opencaption/E2eAudioInput.kt','android/app/src/main/kotlin/dev/opencaption/opencaption/E2eProtocol.kt','android/app/src/main/kotlin/dev/opencaption/opencaption/E2ePreservedNames.kt',str((O/'V020Diagnostic11Input.kt').relative_to(R))]
 cmd=[J,'-Xmx256m','-cp',':'.join(cp),'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler','-no-stdlib','-no-reflect','-jvm-target','17','-classpath',':'.join(cp[1:]),'-d',str(classes)]+[str(R/p) for p in src]
 subprocess.run(cmd,check=True);runtime=str(classes)+':'+cp[1]
 subprocess.run([str(pathlib.Path(J).with_name('javac')),'-cp',runtime,'-d',str(classes),str(R/'evaluation/V020ProtocolBridge.java')],check=True)
 (O/'classpath.txt').write_text(runtime)
 b=Protocol()
 try:prompts=dict(zip(['system','request'],b.prompt()))
 finally:b.close()
 q=read(R/'evaluation/results/v020-evidence11/qualification.json');cases=q['selected'];assert {c['id'] for c in cases}==set(UNITS)
 import wave
 (O/'audio').mkdir();(O/'pcm').mkdir()
 for c in cases:
  p=R/c['audio_path'];assert sha(p)==c['audio_sha256']
  with wave.open(str(p),'rb') as w:
   assert w.getparams()[:3]==(1,2,16000);data=w.readframes(w.getnframes())
  pcm=O/'pcm'/f"{c['id']}.pcm";pcm.write_bytes(data);target=O/'audio'/f"{c['id']}.wav"
  subprocess.run([J,'-Xmx64m','-cp',runtime,'V020Diagnostic11Input',str(pcm),str(target)],check=True)
  c.update(product_path=str(target.relative_to(R)),product_sha256=sha(target),semantic_units=UNITS[c['id']],primary=c['id'] not in [1908,1978])
 order=[]
 for i,c in enumerate(cases):
  for mode in (['audio','text_reference'] if i%2==0 else ['text_reference','audio']):order.append(dict(index=len(order),case_id=c['id'],mode=mode))
 put('score_spec.json',dict(units=UNITS,states=['preserved','omitted','contradicted','uncertain'],unknown_not_correct=True,primary_ids=[1860,1870,1889,1941,1957,1972],primary_units=16,total_cases=8,context_unknown_id=1908,conflicting_human_translation_id=1978,all_cases_coverage_required=True,AI_assisted_not_independent_human=True,additional_facts_make_whole_sentence_fail=True,case1978_english_source_diagnostic_only=True,case1908_objects_sense_not_required=True,classes_can_overlap_report_intersections=True))
 files=dict(im['compiler_files'])
 paths=[R/p for p in src]+[backend,capture,R/'evaluation/V020ProtocolBridge.java',O/'score_spec.json',O/'classpath.txt',R/'evaluation/results/v020-evidence11/qualification.json',R/'evaluation/results/v020-evidence11/reference_audit.json',R/'docs/dev/archive/v0.2.0第11轮新材料诊断计划.md',R/'scripts/run-v020-diagnostic11']
 paths+=list((R/'evaluation').glob('*.py'))+list(classes.rglob('*.class'))+[R/c['product_path'] for c in cases]+[R/c['audio_path'] for c in cases]
 import litert_lm
 paths+=list(pathlib.Path(litert_lm.__file__).parent.rglob('*.py'))
 files.update({str(p):sha(p) for p in paths})
 put('manifest.json',dict(files=files,cases=cases,order=order,prompts=prompts,text_system=TEXT_SYSTEM,model_sha256=sha(MODEL),requests=16,batches=[8,8],retries=0,residencies=1,config=dict(context=768,output=128,threads=4,top_k=1,temperature=0,speculative_decoding=None),no_candidate=True,no_independent_confirmation=True))
 put('compile.json',dict(command=cmd,current_exact_wav=method,product_edited=False));print('FROZEN 8pairs16requests;0 Engine initializations',flush=True)
def verify():
 guard();m=read(O/'manifest.json')
 for p,h in m['files'].items():assert sha(pathlib.Path(p))==h,p
 assert sha(MODEL)==m['model_sha256'];assert TEXT_SYSTEM==m['text_system']
 return m
def serve():
 m=verify();assert not (O/'requests.jsonl').exists(),'No implicit retries/restarts';permit(0)
 from v020_fleurs_pilot import resources
 from gemma_replay import LiteRtRuntime
 log(dict(type='metadata',manifest_sha256=sha(O/'manifest.json'),resources=resources()));b=Protocol();model=None
 try:
  t=time.monotonic();model=LiteRtRuntime(SimpleNamespace(model=MODEL,threads=4,max_new_tokens=128,hints='',task='bilingual',task_profile='baseline',system_profile='minimal',cache_mode='disk',speculative_decoding='default',max_context_tokens=768));model.system_message=m['prompts']['system'];model.prompt=m['prompts']['request'];log(dict(type='loaded',load_ms=(time.monotonic()-t)*1000));print('READY',flush=True)
  cases={c['id']:c for c in m['cases']}
  for batch in range(2):
   command=O/'commands'/str(batch);deadline=time.monotonic()+180
   while not command.exists():
    guard()
    if time.monotonic()>deadline:raise TimeoutError('No command180s')
    time.sleep(.25)
   assert command.read_text().strip()==f'batch {batch}';guard();permit(batch)
   for item in m['order'][batch*8:(batch+1)*8]:
    guard();c=cases[item['case_id']];log(dict(type='started',**item));t=time.monotonic()
    if item['mode']=='audio':
     path=R/c['product_path'];assert sha(path)==c['product_sha256'];raw=model.infer(path);result=dict(raw=raw,inference_ms=(time.monotonic()-t)*1000,**b.parse(raw))
    else:result=text_infer(model,c['reference_en'])
    log(dict(type='request',**item,**result))
   log(dict(type='batch_complete',batch=batch,done=(batch+1)*8,resources=resources()));print(f'BATCH_COMPLETE {batch}',flush=True)
  log(dict(type='complete',requests=16,resources=resources()));print('COMPLETE16',flush=True)
 except BaseException as e:log(dict(type='failure',error=repr(e)));raise
 finally:
  if model is not None:model.close()
  b.close()
if __name__=='__main__':{'prepare':prepare,'verify':verify,'serve':serve}[sys.argv[1]]()
