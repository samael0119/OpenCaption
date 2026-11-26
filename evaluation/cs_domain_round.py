"""Fresh paired audio evaluation through actual Kotlin protocol and Dart controller.
Offline fixed-fallback segmentation; does not measure Android capture/queue/UI.
"""
import argparse,base64,hashlib,json,shutil,subprocess,time,wave
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evaluation/results/cs-domain-20261020/product_round_v2'
JAVA='/home/hyh/Tools/java/eclipse-temurin-jdk17/bin/java'
MODEL=Path('/home/hyh/Tools/litert/models/gemma-4-E2B-it.litertlm')
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
def write(p,v):
 with p.open('x') as f:json.dump(v,f,ensure_ascii=False,indent=2)
def read(p):return json.loads(p.read_text())
def append(v):
 with (OUT/'requests.jsonl').open('a') as f:f.write(json.dumps(v,ensure_ascii=False)+'\n')
def resources():
 rel=next(x for x in Path('/proc/self/cgroup').read_text().splitlines() if x.startswith('0::')).split('::')[1]
 p=Path('/sys/fs/cgroup')/rel.lstrip('/')
 v={k:(p/k).read_text().strip() for k in ['memory.max','memory.swap.max','memory.peak','memory.events']}
 if v['memory.max']=='max' or int(v['memory.max'])>6*1024**3 or v['memory.swap.max']!='0':raise RuntimeError('Expected <=6GiB, swap0')
 return v
class Bridge:
 def __init__(self):
  self.p=subprocess.Popen([JAVA,'-Xmx64m','-cp',(OUT/'classpath.txt').read_text(),'CsDomainBridge',str(OUT/'names.txt')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
 def call(self,*args):
  self.p.stdin.write('\t'.join(args)+'\n');self.p.stdin.flush();line=self.p.stdout.readline()
  if not line:raise RuntimeError('Native bridge exited')
  return line.rstrip('\n').split('\t')
 def close(self):
  self.p.stdin.close();assert self.p.wait(timeout=10)==0
enc=lambda s:base64.b64encode(s.encode()).decode()
dec=lambda s:base64.b64decode(s).decode()
def prepare():
 if (OUT/'manifest.json').exists():raise RuntimeError('Already frozen')
 OUT.mkdir(parents=True,exist_ok=True)
 for s in ['commands','responses','audio','classes']: (OUT/s).mkdir(exist_ok=True)
 from v020_pcm10_prepare import extract
 native=ROOT/'android/app/src/main/kotlin/dev/opencaption/opencaption'
 backend=ROOT/'android/app/src/gemmaE2E/kotlin/dev/opencaption/opencaption/FlavorBackendFactory.kt'
 method=extract(backend.read_text(),'private fun wav(samples: FloatArray): ByteArray')
 kt='''import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.io.File
import dev.opencaption.opencaption.*
object CsInput {
'''+method+'''
@JvmStatic fun main(args:Array<String>){
 val bytes=File(args[0]).readBytes();val b=ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
 val x=FloatArray(bytes.size/2){b.short/32768f};val segmenter=E2eSegmenter();var i=0
 fun emit(v:E2eSegmenter.Boundary){i++;val f=File(args[1],"$i.wav");f.writeBytes(wav(E2eAudioInput.prepareShort(x.copyOfRange(v.start.toInt(),v.end.toInt()))));println("$i\\t${v.start/16}\\t${v.end/16}\\t${v.reason}\\t${f.absolutePath}")}
 var total=0;while(total<x.size){total=minOf(total+320,x.size);segmenter.update(total.toLong(),null)?.let{emit(it)}}
 segmenter.flush(x.size.toLong())?.let{emit(it)}
}}
'''
 (OUT/'CsInput.kt').write_text(kt)
 compiler=read(ROOT/'evaluation/results/v020-integrity8/manifest.json')['compiler_files']
 for p,d in compiler.items():assert sha(p)==d
 cp=list(compiler);classes=OUT/'classes'
 sources=[native/(s+'.kt') for s in ['E2eProtocol','E2ePreservedNames','E2eAudioInput','E2eAudioPolicy','E2eHintPolicy','CaptionStyle']]+[OUT/'CsInput.kt']
 subprocess.run([JAVA,'-Xmx256m','-cp',':'.join(cp),'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler','-no-stdlib','-no-reflect','-jvm-target','17','-classpath',':'.join(cp[1:]),'-d',str(classes),*map(str,sources)],check=True)
 runtime=str(classes)+':'+cp[1];(OUT/'classpath.txt').write_text(runtime)
 subprocess.run([str(Path(JAVA).with_name('javac')),'-cp',runtime,'-d',str(classes),str(ROOT/'evaluation/CsDomainBridge.java')],check=True)
 scope=read(OUT.parent/'scope_60s.json');sources_metadata=[]
 for s in scope['sources']:
  assert sha(s['path'])==s['sha256']
  folder=OUT/'audio'/s['source_id'];folder.mkdir(exist_ok=True)
  pcm=folder/'source.pcm'
  subprocess.run(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-i',s['path'],'-t',str(s['end_seconds']),'-ar','16000','-ac','1','-f','s16le',str(pcm)],check=True)
  lines=subprocess.check_output([JAVA,'-Xmx96m','-cp',runtime,'CsInput',str(pcm),str(folder)],text=True)
  windows=[]
  for line in lines.splitlines():
   idx,start,end,reason,p=line.split('\t');windows.append(dict(window=int(idx),start_ms=int(start),end_ms=int(end),boundary_reason=reason,path=p,sha256=sha(p)))
  sources_metadata.append(dict(source_id=s['source_id'],role=s['role'],windows=windows))
 shutil.copyfile(ROOT/'evaluation/private/cs_domain_reference_v3.json',OUT/'reference.json')
 paths=sources+[backend,ROOT/'evaluation/CsDomainBridge.java',ROOT/'evaluation/cs_domain_round.py',ROOT/'test/cs_domain_live_eval_test.dart',ROOT/'evaluation/private/cs_domain_reference_v3.json']
 paths+=list((ROOT/'lib/core').glob('*.dart'))+list((ROOT/'assets/corpora').rglob('*.json'))+list(classes.rglob('*.class'))
 m=dict(version=1,scope='AI-assisted development regression; offline CPU; fixed fallback real E2eSegmenter; no Android capture/queue/UI or phone latency',arms=['no_corpus','cs2_auto'],sources=sources_metadata,request_budget=2*sum(len(s['windows']) for s in sources_metadata),files={str(p):sha(p) for p in paths},model_sha256=sha(MODEL),config=dict(context=768,output=128,cpu_threads=4,temperature=0,speculative='Python SDK default; Android experimental speculative decoding not reproduced'),references_in_prompts=False)
 write(OUT/'manifest.json',m);print(json.dumps(dict(request_budget=m['request_budget'],windows=[(s['source_id'],len(s['windows'])) for s in sources_metadata])))
def serve():
 m=read(OUT/'manifest.json')
 if (OUT/'requests.jsonl').exists():raise RuntimeError('Already started; no implicit retry')
 for p,d in m['files'].items():
  if sha(p)!=d:raise RuntimeError('Frozen source mismatch '+p)
 assert sha(MODEL)==m['model_sha256']
 append(dict(type='metadata',manifest_sha256=sha(OUT/'manifest.json'),resources=resources()))
 deadline=time.monotonic()+120
 while not (OUT/'names.txt').exists():
  if time.monotonic()>deadline:raise TimeoutError('No Dart controller')
  time.sleep(.1)
 import litert_lm as api
 from gemma_replay import response_text
 model=None;bridge=Bridge();cooldowns={}
 try:
  t=time.monotonic();(OUT/'cache').mkdir(exist_ok=True)
  model=api.Engine(str(MODEL),backend=api.Backend.CPU(thread_count=4),audio_backend=api.Backend.CPU(thread_count=4),max_num_tokens=768,cache_dir=str(OUT/'cache'),enable_speculative_decoding=None)
  append(dict(type='loaded',load_ms=(time.monotonic()-t)*1000));print('READY',flush=True)
  for sequence in range(m['request_budget']):
   p=OUT/'commands'/f'{sequence:04}.json';deadline=time.monotonic()+120
   while not p.exists():
    if time.monotonic()>deadline:raise TimeoutError('Controller request deadline')
    time.sleep(.05)
   r=read(p);assert r['sequence']==sequence
   assert r['arm'] in m['arms']
   assert len(r['proposed_hints'])<=240
   assert sha(r['path'])==r['sha256']
   chosen,verification=bridge.call('choose',str(r['window']),enc(r['proposed_hints']),str(r['automatic']).lower());hints=dec(chosen)
   system,prompt=[dec(v) for v in bridge.call('prompt',chosen)]
   append(dict(type='started',sequence=sequence,arm=r['arm'],source_id=r['source_id'],window=r['window'],hints=hints))
   t=time.monotonic()
   with model.create_conversation(system_message=system,thinking_config=api.ThinkingConfig(False,0),sampler_config=api.SamplerConfig(top_k=1,top_p=1.,temperature=0.),max_output_tokens=128) as c:
    raw=response_text(c.send_message(api.Contents.of(prompt,api.Content.AudioFile(r['path'])),max_output_tokens=128,thinking_config=api.ThinkingConfig(False,0)))
   elapsed=(time.monotonic()-t)*1000
   f=bridge.call('parse',chosen,enc(raw));result=dict(sequence=sequence,status=f[0],raw=raw,inference_ms=elapsed,applied_hints=hints,verification=verification=='true',english='',chinese='',styles={})
   if f[0]=='subtitle':
    en,zh=dec(f[1]),dec(f[2]);result.update(english=en,chinese=zh)
    for style in ['standard','natural','community']:
     key=(r['arm'],r['source_id'],style);allowed=r['start_ms']-cooldowns.get(key,-30000)>=30000
     g=bridge.call('render',enc(en),enc(zh),style,str(style=='community').lower(),str(r['arm']=='cs2_auto').lower(),str(allowed).lower())
     result['styles'][style]=dict(chinese=dec(g[0]),nicknames=int(g[1]),playful=g[2]=='true',localized=int(g[3]))
     if g[2]=='true':cooldowns[key]=r['end_ms']
   elif f[0]=='invalid':result['reason']=dec(f[1])
   append({'type':'request',**r,**result})
   temp=OUT/'responses'/f'{sequence:04}.tmp';temp.write_text(json.dumps(result,ensure_ascii=False));temp.rename(temp.with_suffix('.json'))
   if (sequence+1)%10==0:print('DONE',sequence+1,flush=True)
  append(dict(type='complete',requests=m['request_budget'],resources=resources()));print('COMPLETE',flush=True)
 except BaseException as e:append(dict(type='failure',error=repr(e)));raise
 finally:
  if model is not None:model.close()
  bridge.close();append(dict(type='closed',resources=resources()))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','serve']);a=p.parse_args();globals()[a.action]()
