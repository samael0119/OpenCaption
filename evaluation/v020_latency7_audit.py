"""Audit actual freshly compiled product replay; no model/time claims."""
import json,math,statistics,hashlib
from pathlib import Path
from collections import defaultdict
from v020_product_queue_summary import cue_times
R=Path(__file__).resolve().parents[1];O=R/'evaluation/results/v020-latency7';S=R/'evaluation/results/s0-20261013'
m=json.loads((O/'manifest.json').read_text())
for p,h in m['files'].items():
 path=Path(p) if p.startswith('/') else R/p
 assert hashlib.sha256(path.read_bytes()).hexdigest()==h,p
segments=defaultdict(list);queues=defaultdict(list)
for l in (O/'product.tsv').read_text().splitlines():
 x=l.split('\t')
 if x[0]=='segment':segments[x[1],int(x[2])].append(dict(start=int(x[3]),end=int(x[4]),reason=x[5]))
 else:queues[x[1],int(x[2]),int(x[3])].append(dict(state=x[4],start_ms=int(x[5]),end_ms=int(x[6]),at=int(x[7])))
# Fixed synthetic expected boundary checks, including unknown/weak no deletion.
for ms in [400,600]:
 for i in range(4):assert [r['end'] for r in segments[f'test{i}',ms]]==[80000,96000]
 assert len(segments['test4',ms])==2
 assert segments['test5',ms][0]['end']==3200+ms*16
 assert len(segments['test6',ms])==1
 assert len(segments['test7',ms])==(2 if ms==400 else 1)
 assert len(segments['test8',ms])==2
 assert segments['test9',ms]==[dict(start=0,end=9600,reason='tail')]
 assert segments['test10',ms]==[dict(start=0,end=80000,reason='maximum')]
 assert len(segments['test11',ms])==2
cues=cue_times(Path('/home/hyh/Downloads/opencaption/clip_gold_bilingual.srt').read_text());assert len(cues)==29
qnt=lambda a,p:sorted(a)[math.ceil(len(a)*p)-1]
summary=dict(new_model_requests=0,synthetic_mechanism_cases=12,compiled_current_product=True,real_traces={},cue_rows={},load_sensitivity=[],not_caption_E2E=True,not_content_quality=True)
for t in m['traces']:
 name=t['name'];summary['real_traces'][name]={}
 old=json.loads((S/(name+'_segments.json')).read_text())
 for ms in [400,600]:
  a=segments[name,ms];assert a[0]['start']==0 and a[-1]['end']==t['samples'];assert all(u['end']==v['start'] for u,v in zip(a,a[1:]))
  olda=old[f'pause_{ms}'];assert [(r['start'],r['end']) for r in a]==[(r['start'],r['end']) for r in olda],(name,ms,'old/current boundary discrepancy')
  lengths=[(r['end']-r['start'])/16 for r in a]
  summary['real_traces'][name][ms]=dict(n=len(a),per_minute=len(a)/(t['samples']/16000)*60,length_P50_ms=statistics.median(lengths),length_P95_ms=qnt(lengths,.95),pause_count=sum(r['reason']=='pause' for r in a),PCM_ownership_complete=True,old_cut_exact_equal=True)
for ms in [600,400]:
 a=segments['clip',ms];rows=[]
 for i,(s,e) in enumerate(cues):
  last=e*16-1;w=next(r for r in a if r['start']<=last<r['end']);cross=sum(s*16<r['end']<e*16 for r in a)
  rows.append(dict(cue=i+1,start_ms=s,end_ms=e,last_sample_submission_ms=w['end']/16,wait_proxy_ms=w['end']/16-e,crossed_boundaries=cross))
 summary['cue_rows'][ms]=rows
 summary.setdefault('wait_proxy',{})[ms]=dict(n=29,P50_ms=statistics.median(r['wait_proxy_ms'] for r in rows),P95_ms=qnt([r['wait_proxy_ms'] for r in rows],.95),crossed_boundaries_total=sum(r['crossed_boundaries'] for r in rows))
for cost in [1000,2000,3000,4000]:
 for ms in [600,400]:
  rs=queues['clip',ms,cost];order=sorted(rs,key=lambda r:r['start_ms']);assert order[0]['start_ms']==0 and order[-1]['end_ms']==m['traces'][0]['samples']//16
  assert all(a['end_ms']==b['start_ms'] for a,b in zip(order,order[1:]))
  drops=[r for r in rs if r['state']!='delivered'];eligible=sum(not any(d['start_ms']<e and d['end_ms']>s for d in drops) for s,e in cues)
  summary['load_sensitivity'].append(dict(service_ms=cost,policy_ms=ms,dropped_ms=sum(r['end_ms']-r['start_ms'] for r in drops),fully_service_eligible_cues=eligible,n_cues=29,simulated_not_real_inference=True))
b=summary['wait_proxy'][600];c=summary['wait_proxy'][400];reduction=b['P50_ms']-c['P50_ms'];growth=summary['real_traces']['clip'][400]['n']/summary['real_traces']['clip'][600]['n']-1
load_ok=True
for cost in [1000,2000,3000,4000]:
 bs=next(r for r in summary['load_sensitivity'] if r['service_ms']==cost and r['policy_ms']==600);cs=next(r for r in summary['load_sensitivity'] if r['service_ms']==cost and r['policy_ms']==400)
 if cs['dropped_ms']>bs['dropped_ms'] or cs['fully_service_eligible_cues']<bs['fully_service_eligible_cues']:load_ok=False
summary['gate']=dict(P50_reduction_ms=reduction,P50_reduction_percent=reduction/b['P50_ms']*100,request_growth_percent=growth*100,P95_nonworse=c['P95_ms']<=b['P95_ms'],load_coverage_nondecreasing=load_ok,passed=reduction>=200 and reduction/b['P50_ms']>=.2 and c['P95_ms']<=b['P95_ms'] and growth<=.25 and load_ok)
(O/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in summary.items() if k!='cue_rows'},ensure_ascii=False,indent=2))
