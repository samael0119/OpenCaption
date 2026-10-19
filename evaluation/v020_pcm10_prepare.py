"""Freeze the exact product float conversion and extracted WAV writer; zero Engine."""
import array,collections,hashlib,json,math,pathlib,subprocess,sys,wave
from v020_redundancy8 import sha,J,R
O=R/'evaluation/results/v020-pcm10'
def put(p,x):
 with p.open('x') as f:json.dump(x,f,ensure_ascii=False,indent=2)
def extract(text,start):
 i=text.index(start);a=text.index('{',i);depth=1;b=a+1
 while depth:
  depth += (text[b]=='{')-(text[b]=='}');b+=1
 return text[i:b]
def samples(p):
 with wave.open(str(p)) as w:
  assert (w.getnchannels(),w.getsampwidth(),w.getframerate())==(1,2,16000);a=array.array('h',w.readframes(w.getnframes()))
 if sys.byteorder!='little':a.byteswap()
 return a
def main():
 O.mkdir(exist_ok=True);assert not (O/'manifest.json').exists()
 state=json.loads((R/'evaluation/results/v020-continuation/state.json').read_text());assert state['status']=='active' and state['current_round']==10
 backend=R/'android/app/src/gemmaE2E/kotlin/dev/opencaption/opencaption/FlavorBackendFactory.kt';capture=R/'android/app/src/main/kotlin/dev/opencaption/opencaption/CaptionEngine.kt'
 assert 'val floats = FloatArray(count) { pcm[it] / 32768f }' in capture.read_text()
 old=extract(backend.read_text(),'private fun wav(samples: FloatArray): ByteArray');assert old.count('(it.coerceIn(-1f, 1f) * 32767).toInt().toShort()')==1
 candidate=old.replace('(it.coerceIn(-1f, 1f) * 32767).toInt().toShort()','(it.coerceIn(-1f, 1f) * 32768).toInt().coerceIn(-32768, 32767).toShort()').replace('fun wav(', 'fun lossless(')
 source='''import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.io.File
import dev.opencaption.opencaption.E2eAudioInput
object V020Pcm10 {
'''+old+'\n'+candidate+'''
 private fun value(w: ByteArray, i: Int): Int = ByteBuffer.wrap(w).order(ByteOrder.LITTLE_ENDIAN).getShort(44+i*2).toInt()
 @JvmStatic fun main(args:Array<String>) {
  if(args[0]=="exhaustive") {
   val x=FloatArray(65536) {(it-32768)/32768f};val a=wav(x);val b=lossless(x)
   var badA=0;var badB=0;var zeroA=0;var zeroB=0;var maxA=0
   for(i in x.indices){val original=i-32768;val aa=value(a,i);val bb=value(b,i)
    if(aa!=original)badA++;if(bb!=original)badB++
    if(original!=0 && aa==0)zeroA++;if(original!=0 && bb==0)zeroB++
    maxA=maxOf(maxA,kotlin.math.abs(aa-original))
   };check(badB==0)
   var tests=0
   fun checkInput(x:FloatArray, n:Int){val p=E2eAudioInput.prepareShort(x);check(p.size==n);check(p.takeLast(x.size).toFloatArray().contentEquals(x));tests++}
   checkInput(floatArrayOf(),0);checkInput(FloatArray(10),10)
   checkInput(floatArrayOf(1/32768f,-1/32768f),32000)
   checkInput(FloatArray(31999){1/32768f},32000);checkInput(FloatArray(32000){1/32768f},32000)
   checkInput(FloatArray(80000){1/32768f},80000)
   check(value(b,0)==-32768 && value(b,65535)==32767);tests++
   check(value(lossless(floatArrayOf(0f)),0)==0);tests++
   check(value(lossless(floatArrayOf(Float.NaN)),0)==value(wav(floatArrayOf(Float.NaN)),0));tests++
   check(value(lossless(floatArrayOf(Float.POSITIVE_INFINITY)),0)==32767);tests++
   check(value(lossless(floatArrayOf(Float.NEGATIVE_INFINITY)),0)==-32768);tests++
   check(value(lossless(floatArrayOf(-2f,2f)),0)==-32768 && value(lossless(floatArrayOf(-2f,2f)),1)==32767);tests++
   println("{\\"values\\":65536,\\"current_errors\\":$badA,\\"candidate_errors\\":$badB,\\"current_nonzero_to_zero\\":$zeroA,\\"candidate_nonzero_to_zero\\":$zeroB,\\"current_max_error\\":$maxA,\\"sequence_checks\\":$tests}")
  } else {
   val bytes=File(args[0]).readBytes();check(bytes.size%2==0);val buf=ByteBuffer.wrap(bytes).order(ByteOrder.LITTLE_ENDIAN)
   val x=FloatArray(bytes.size/2){buf.short/32768f};val p=E2eAudioInput.prepareShort(x)
   File(args[1]).writeBytes(wav(p));File(args[2]).writeBytes(lossless(p))
  }
 }
}
'''
 (O/'V020Pcm10.kt').write_text(source);put(O/'source_extraction.json',dict(backend=str(backend.relative_to(R)),sha256=sha(backend),capture_sha256=sha(capture),exact_current_wav=old,candidate_wav=candidate,note='Extracted exact function, not an Android service build. NaN->0 preserved; negative saturation becomes -32768 as intended PCM lower endpoint.'))
 im=json.loads((R/'evaluation/results/v020-integrity8/manifest.json').read_text());cp=list(im['compiler_files']);classes=O/'classes';classes.mkdir()
 for p,h in im['compiler_files'].items():assert sha(pathlib.Path(p))==h
 src=['android/app/src/main/kotlin/dev/opencaption/opencaption/E2eAudioInput.kt','android/app/src/main/kotlin/dev/opencaption/opencaption/E2eProtocol.kt','android/app/src/main/kotlin/dev/opencaption/opencaption/E2ePreservedNames.kt',str((O/'V020Pcm10.kt').relative_to(R))]
 cmd=[J,'-Xmx256m','-cp',':'.join(cp),'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler','-no-stdlib','-no-reflect','-jvm-target','17','-classpath',':'.join(cp[1:]),'-d',str(classes)]+[str(R/p) for p in src];subprocess.run(cmd,check=True)
 runtime=str(classes)+':'+cp[1];subprocess.run([str(pathlib.Path(J).with_name('javac')),'-cp',runtime,'-d',str(classes),str(R/'evaluation/V020ProtocolBridge.java')],check=True);(O/'classpath.txt').write_text(runtime)
 java=[J,'-Xmx96m','-cp',runtime,'V020Pcm10'];ex=json.loads(subprocess.check_output(java+['exhaustive'],text=True));assert ex['sequence_checks']==12;put(O/'exhaustive.json',ex)
 oldm=json.loads((R/'evaluation/results/v020-redundancy8/P0_manifest.json').read_text());cases=[]
 (O/'audio').mkdir();(O/'pcm').mkdir()
 for c in oldm['cases']:
  p=R/c['path'];assert sha(p)==c['sha256'];original=samples(p);pcm=O/'pcm'/f"{c['id']}.pcm";pcm.write_bytes(original.tobytes());a=O/'audio'/f"{c['id']}-current.wav";b=O/'audio'/f"{c['id']}-candidate.wav"
  subprocess.run(java+[str(pcm),str(a),str(b)],check=True);aa=samples(a);bb=samples(b);pad=len(bb)-len(original);assert pad>=0 and bb[pad:]==original and all(z==0 for z in bb[:pad]);assert len(aa)==len(bb)
  def rms(z):return math.sqrt(sum(v*v for v in z)/len(z))
  cc=dict(c);cc.update(current_path=str(a.relative_to(R)),candidate_path=str(b.relative_to(R)),current_sha256=sha(a),candidate_sha256=sha(b),original_samples=len(original),padded_samples=pad,current_changed=sum(v!=w for v,w in zip(original,aa[pad:])),current_erased_nonzero=sum(v!=0 and w==0 for v,w in zip(original,aa[pad:])),candidate_equals_original_suffix=True,rms_original=rms(original),rms_current_suffix=rms(aa[pad:]),rms_candidate_suffix=rms(bb[pad:]));cases.append(cc)
 selected=[]
 for g,n in [('fleurs_semantic',6),('natural_whisper',2),('music',1),('known_short_music',1)]:selected += [c for c in cases if c['group']==g][:n]
 selected += [next(c for c in cases if c['group']=='ordinary'),next(c for c in cases if str(c['id'])=='1272-135031-0009')];assert len(selected)==12
 order=[]
 for i,c in enumerate(selected):
  for mode in (['current','candidate'] if i%2==0 else ['candidate','current']):order.append(dict(index=len(order),case_id=c['id'],group=c['group'],mode=mode))
 files=dict(im['compiler_files']);paths=src+[str(capture.relative_to(R)),str(backend.relative_to(R)),'evaluation/v020_pcm10_prepare.py','evaluation/v020_pcm10.py','evaluation/gemma_replay.py','evaluation/v020_redundancy8.py','evaluation/V020ProtocolBridge.java','docs/dev/archive/v0.2.0第10轮PCM往返保真计划.md','scripts/run-v020-pcm10']
 for c in cases:paths.extend([c['path'],c['current_path'],c['candidate_path']])
 files.update({p:sha(R/p) for p in paths});files.update({str(p.relative_to(R)):sha(p) for p in classes.rglob('*.class')});files[str((O/'classpath.txt').relative_to(R))]=sha(O/'classpath.txt')
 import litert_lm
 files.update({str(p):sha(p) for p in pathlib.Path(litert_lm.__file__).parent.rglob('*.py')})
 for p in ['evaluation/results/v020-round3/candidate1/frozen_ratings.json','evaluation/v020_semantic_rating_cache.py']:files[p]=sha(R/p)
 put(O/'manifest.json',dict(files=files,all41=cases,cases=selected,order=order,model_sha256=oldm['model_sha256'],prompts=oldm['prompts'],config=oldm['config'],budget=dict(P1=24,batches=[8,8,8],conditional_remaining=58,independent=0,retries=0,residencies=1),exhaustive=ex,product_source_unchanged=True))
 put(O/'compile.json',dict(command=cmd));print(json.dumps(dict(exhaustive=ex,files=41,changed=sum(c['current_changed'] for c in cases),erased=sum(c['current_erased_nonzero'] for c in cases),padding=[(c['id'],c['padded_samples']) for c in cases if c['padded_samples']],new_model_requests=0),ensure_ascii=False))
if __name__=='__main__':main()
