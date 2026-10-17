import json,hashlib,wave
from pathlib import Path
R=Path(__file__).resolve().parents[1];B=R/'evaluation/results/s0-20261013';O=R/'evaluation/results/v020-latency7'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
files={};rows=[];meta=[]
for name in ['clip','clip_match_demo2','clip_match_demo3','clip_interview_niko']:
 wav=B/(name+'.wav');p=B/(name+'_vad.json');cuts=B/(name+'_segments.json')
 with wave.open(str(wav)) as w:
  assert (w.getnchannels(),w.getframerate(),w.getsampwidth())==(1,16000,2);n=w.getnframes();pcm=w.readframes(n)
 probs=json.loads(p.read_text())
 assert len(probs)==(n+511)//512
 for t in range(320,n+320,320):
  t=min(t,n);completed=t//512;v=probs[completed-1] if completed else 0
  assert completed*512<=t
  rows.append(f'{name}\t{t}\t{v}')
 meta.append(dict(name=name,samples=n,pcm_sha256=hashlib.sha256(pcm).hexdigest(),complete_frames=n//512,padded_final_probability_unused=(n%512!=0)))
 for x in [wav,p,cuts]:files[str(x.relative_to(R))]=sha(x)
tests=[([1.0]*300),([0.1]*300),([None]*300),([float('nan')]*300),([0.0]*100+[1.0]*20+[0.0]*40),([1.0]*10+[0.0]*50),([1.0]*10+[0.0]*15+[1.0]*50),([1.0]*10+[0.0]*20+[1.0]*50),([1.0]*10+[0.0]*30+[1.0]*50),([0.0]*23+[1.0]*7),([1.0]*250),([1.0]*10+[None]*100+[0.0]*100)]
for i,ps in enumerate(tests):
 for j,p in enumerate(ps):rows.append(f'test{i}\t{(j+1)*320}\t'+('null' if p is None else 'nan' if p!=p else str(p)))
(O/'frames.tsv').write_text('\n'.join(rows)+'\n')
for x in ['android/app/src/main/kotlin/dev/opencaption/opencaption/E2eAudioPolicy.kt','android/app/src/main/kotlin/dev/opencaption/opencaption/SileroBoundaryVad.kt','evaluation/V020Latency7.kt','evaluation/v020_latency7_prepare.py','evaluation/v020_product_queue_summary.py','docs/v0.2.0第7轮延迟归因计划.md']:
 files[x]=sha(R/x)
p=Path('/home/hyh/Downloads/opencaption/clip_gold_bilingual.srt');files[str(p)]=sha(p);files[str((O/'frames.tsv').relative_to(R))]=sha(O/'frames.tsv')
(O/'manifest.json').write_text(json.dumps(dict(files=files,traces=meta,synthetic_cases=12,candidates_ms=[600,400],new_model_requests=0,mapping='completed=floor(total_samples/512); only completed-1 cached VAD; partial final padded VAD unused',gate='SRT end-to-submit proxy P50 -20% and -200ms; P95 no worse; requests<=+25%; queue grid coverage no drop'),indent=2)+'\n')
