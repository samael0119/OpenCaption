"""Zero-Gemma compilation and request-count freeze for bounded development replay."""
import hashlib,json,subprocess,wave,re
from pathlib import Path
from v020_pcm10_prepare import extract
R=Path(__file__).resolve().parents[1];O=R/'evaluation/results/v020-delivery/B'
JAVA='/home/hyh/Tools/java/eclipse-temurin-jdk17/bin/java'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(name,row):(O/name).write_text(json.dumps(row,ensure_ascii=False,indent=2)+'\n')
def main():
 state=json.loads((R/'evaluation/results/v020-continuation/state.json').read_text())
 assert state['status']=='active' and state['delivery_scope']['execution_authorized']
 assert not (O/'prepare_manifest.json').exists(),'Already frozen: no implicit replay'
 O.mkdir(parents=True,exist_ok=True)
 backend=R/'android/app/src/gemmaE2E/kotlin/dev/opencaption/opencaption/FlavorBackendFactory.kt'
 wavmethod=extract(backend.read_text(),'private fun wav(samples: FloatArray): ByteArray')
 assert '* 32767).toInt().toShort()' in wavmethod
 kt=O/'V020DeliveryBInput.kt'
 kt.write_text('import java.nio.ByteBuffer\nimport java.nio.ByteOrder\nimport java.io.File\nobject V020DeliveryBInput {\n'+wavmethod+'\n@JvmStatic fun save(path:String, samples:FloatArray) { File(path).writeBytes(wav(samples)) }\n}\n')
 old=(R/'evaluation/V020JointCaptureBridge.java').read_text()
 i=old.index('  static void wav(');j=old.index('  public static void main',i)
 source=old[:i]+'  static void wav(Path path,float[] pcm) throws Exception { V020DeliveryBInput.save(path.toString(),pcm); }\n'+old[j:]
 source=source.replace('public final class V020JointCaptureBridge','public final class V020DeliveryBCapture')
 source=source.replace('int seconds=Integer.parseInt(args[3]);','int seconds=Integer.parseInt(args[3]); String strategy=args[4]; boolean plan=args[5].equals("plan");\n    if(!Set.of("fixed","pause").contains(strategy)) throw new IllegalArgumentException("strategy");')
 pos=source.index('    queue.reset(1);')
 branch='''    if(cycle.length!=seconds*16000) throw new IllegalArgumentException("exact non-looping input");
    if(plan) {
      try(var vad=new SileroBoundaryVad(Files.readAllBytes(root.resolve("android/app/src/main/assets/vad/silero_v6_2_1.onnx")))) {
        var segmenter=new E2eSegmenter(9600,80000);
        for(int f=0;f<seconds*50;f++) {
          float[] pcm=Arrays.copyOfRange(cycle,f*320,(f+1)*320);
          var probability=vad.observe(pcm);
          var b=segmenter.update((f+1)*320L,strategy.equals("pause")?probability:null);
          if(b!=null) emit("BOUNDARY\\t"+b.getStart()+"\\t"+b.getEnd()+"\\t"+b.getReason());
        }
        var b=segmenter.flush(cycle.length);
        if(b!=null) emit("BOUNDARY\\t"+b.getStart()+"\\t"+b.getEnd()+"\\t"+b.getReason());
      }
      return;
    }
    var preparedVad=new SileroBoundaryVad(Files.readAllBytes(root.resolve("android/app/src/main/assets/vad/silero_v6_2_1.onnx")));
'''
 source=source[:pos]+branch+source[pos:]
 source=source.replace('origin=System.nanoTime();','origin=System.nanoTime(); emit("CLOCK\\t"+clock());')
 source=source.replace('try(var vad=new SileroBoundaryVad(Files.readAllBytes(root.resolve("android/app/src/main/assets/vad/silero_v6_2_1.onnx")))) {\n      var buffer=', 'try(var vad=preparedVad) {\n      var buffer=')
 source=source.replace('cycle[(frame*320+j)%cycle.length]','cycle[frame*320+j]')
 source=source.replace('var boundary=segmenter.update(buffer.getTotal(),vad.observe(pcm));','var probability=vad.observe(pcm);\n        var boundary=segmenter.update(buffer.getTotal(),strategy.equals("pause")?probability:null);')
 source=source.replace('actual model + Dart/widget acknowledgement','actual model-completion acknowledgement (UI is asynchronous)')
 (O/'V020DeliveryBCapture.java').write_text(source)
 proto=(R/'evaluation/V020JointProtocolBridge.java').read_text().replace('public class V020JointProtocolBridge','public class V020DeliveryBProtocol')
 proto=proto.replace('      String hints=V020ProtocolBridge.decode(f[2]);','''      if(f[0].equals("choose")) {
        var d=E2eHintPolicy.INSTANCE.choose(Long.parseLong(f[1]),V020ProtocolBridge.decode(f[2]),Boolean.parseBoolean(f[3]));
        System.out.println(V020ProtocolBridge.encode(d.getHints())+"\\t"+d.getVerification()); System.out.flush();continue;
      }
      String hints=V020ProtocolBridge.decode(f[2]);''')
 (O/'V020DeliveryBProtocol.java').write_text(proto)
 im=json.loads((R/'evaluation/results/v020-integrity8/manifest.json').read_text());compiler=list(im['compiler_files'])
 for p,h in im['compiler_files'].items():assert sha(p)==h
 ort=R/'evaluation/results/onnxruntime-1.22.0.jar';classes=O/'classes';classes.mkdir()
 names=['AudioBuffer','E2eAudioPolicy','E2eAudioInput','E2eHintPolicy','E2ePreservedNames','E2eProtocol','SileroBoundaryVad']
 src=[R/f'android/app/src/main/kotlin/dev/opencaption/opencaption/{n}.kt' for n in names]+[kt]
 cmd=[JAVA,'-Xmx256m','-cp',':'.join(compiler),'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler','-no-stdlib','-no-reflect','-jvm-target','17','-classpath',':'.join(compiler[1:])+':'+str(ort),'-d',str(classes)]+[str(p) for p in src]
 subprocess.run(cmd,check=True)
 cp=str(classes)+':'+compiler[1]+':'+str(ort)
 subprocess.run([str(Path(JAVA).with_name('javac')),'-J-Xmx128m','-cp',cp,'-d',str(classes),str(R/'evaluation/V020ProtocolBridge.java'),str(O/'V020DeliveryBProtocol.java'),str(O/'V020DeliveryBCapture.java')],check=True)
 (O/'classpath.txt').write_text(cp)
 oldnames=R/'evaluation/results/v020-independent/joint_live_names.txt';assert oldnames.exists();(O/'names.txt').write_bytes(oldnames.read_bytes())
 canonical=R/'evaluation/results/s0-20261013/clip.wav'
 with wave.open(str(canonical)) as w:
  assert w.getparams()[:3]==(1,2,16000);original_frames=w.getnframes();data=w.readframes(120*16000)
 assert len(data)==120*16000*2
 pieces=[];all_order=[]
 for i in range(4):
  audio=O/f'piece-{i}.wav'
  with wave.open(str(audio),'wb') as w:w.setparams((1,2,16000,0,'NONE',''));w.writeframes(data[i*30*16000*2:(i+1)*30*16000*2])
  counts={};cuts={}
  for strategy in ['fixed','pause']:
   proc=subprocess.run([JAVA,'-Xmx128m','-cp',cp,'V020DeliveryBCapture',str(R),str(audio),str(O/'current_input.wav'),'30',strategy,'plan'],check=True,capture_output=True,text=True)
   (O/f'piece-{i}-{strategy}-plan.log').write_text(proc.stdout+proc.stderr)
   boundaries=[]
   for line in proc.stdout.splitlines():
    f=line.split('\t');assert f[0]=='BOUNDARY';boundaries.append({'start_sample':int(f[1]),'end_sample':int(f[2]),'reason':f[3]})
   assert boundaries[0]['start_sample']==0 and boundaries[-1]['end_sample']==480000
   assert all(a['end_sample']==b['start_sample'] for a,b in zip(boundaries,boundaries[1:]))
   cuts[strategy]=boundaries;counts[strategy]=len(boundaries)
  assert max(counts.values())<=10,('Cannot freeze legal batch size',i,counts)
  piece={'id':i,'absolute_start_ms':i*30000,'duration_ms':30000,'path':str(audio.relative_to(R)),'sha256':sha(audio),'boundaries':cuts,'request_upper_bounds':counts,'artificial_boundary_reset':True};pieces.append(piece)
  for mode in (['fixed','pause'] if i%2==0 else ['pause','fixed']):all_order.append({'batch':len(all_order),'piece':i,'strategy':mode,'max_requests':counts[mode]})
 srt=Path('/home/hyh/Downloads/opencaption/clip_gold_bilingual.srt');notes=Path('/home/hyh/Downloads/opencaption/clip_gold_alignment_notes.txt')
 def ms(s):
  h,m,sec,mil=map(int,re.split('[:,]',s));return ((h*60+m)*60+sec)*1000+mil
 units=[]
 for b in re.split(r'\n\s*\n',srt.read_text(encoding='utf-8-sig').strip()):
  ls=b.splitlines();a,z=ls[1].split(' --> ');start,end=ms(a),ms(z)
  units.append({'id':int(ls[0]),'start_ms':start,'end_ms':end,'english':ls[2],'chinese':'\n'.join(ls[3:]),'crosses_artificial_boundary':start//30000!=(max(start,end-1))//30000,'outside_first120s':end>120000})
 save('reference_proxy.json',{'source':str(srt),'sha256':sha(srt),'notes':str(notes),'notes_sha256':sha(notes),'classification':'ASR-timed and assisted correction per accompanying notes; not independent human gold','semantic_end_time_human_verified':False,'items':units,'formal_latency_quality_eligible':False,'unknowns_and_cross_boundary_units_retained':True})
 total=sum(x['max_requests'] for x in all_order);assert total<=80 and total<=400
 paths=src+[backend,R/'evaluation/V020ProtocolBridge.java',R/'evaluation/V020JointCaptureBridge.java',R/'evaluation/V020JointProtocolBridge.java',O/'V020DeliveryBCapture.java',O/'V020DeliveryBProtocol.java',O/'names.txt',O/'classpath.txt',O/'reference_proxy.json',canonical,srt,notes,ort,R/'android/app/src/main/assets/vad/silero_v6_2_1.onnx',R/'evaluation/v020_delivery_B_prepare.py']+list(classes.rglob('*.class'))+[R/p['path'] for p in pieces]
 files=dict(im['compiler_files']);files.update({str(p):sha(p) for p in paths})
 save('prepare_manifest.json',{'files':files,'pieces':pieces,'order':all_order,'request_upper_bound':total,'batches':len(all_order),'max_batch_size':max(x['max_requests'] for x in all_order),'original_canonical_frames':original_frames,'screening_samples':1920000,'trailing_samples_not_played':original_frames-1920000,'source_role':'old development, new measurement only','formal_independent_confirmation':False,'new_model_requests':0,'current_exact_wav_method':wavmethod,'ui_ack_can_block_worker':False,'clock_rule':'Python before-BEGIN/Java CLOCK/Python receive bounds; browser offset interval, no wall-clock mixing','same_6GiB_pipeline_required':True,'runner_manifest_still_required_before_inference':True})
 save('compile.json',{'command':cmd,'model_initialized':False});print(json.dumps({'pieces':4,'batches':len(all_order),'request_upper_bound':total,'counts':[p['request_upper_bounds'] for p in pieces],'new_model_requests':0,'reference':'ASR-assisted proxy, not human gold'}))
if __name__=='__main__':main()
