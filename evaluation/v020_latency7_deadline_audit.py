"""Audit deadline experiment against frozen gates; no content or E2E rating."""
import json,hashlib,statistics,math
from pathlib import Path
from collections import defaultdict
from v020_product_queue_summary import cue_times
R=Path(__file__).resolve().parents[1];B=R/'evaluation/results/v020-latency7';O=B/'deadline'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
m=json.loads((O/'manifest.json').read_text())
for p,h in m['files'].items():assert sha(Path(p) if p.startswith('/') else R/p)==h,p
seg=defaultdict(list);queue=defaultdict(list)
for l in (O/'product.tsv').read_text().splitlines():
 x=l.split('\t')
 if x[0]=='segment':seg[x[1],x[2]].append(dict(start=int(x[3]),end=int(x[4]),reason=x[5]))
 else:queue[x[1],x[2],int(x[3])].append(dict(state=x[4],start=int(x[5]),end=int(x[6]),at=int(x[7])))
for policy in ['baseline','anchored']:
 for i in range(4):assert [r['end'] for r in seg[f'test{i}',policy]]==[80000,96000]
 assert seg['test5',policy][0]['end']==12800
 assert len(seg['test6',policy])==1
 assert seg['test8',policy][0]==dict(start=0,end=80000,reason='maximum')
 assert seg['test9',policy]==[dict(start=0,end=9600,reason='tail')]
 assert seg['test10',policy]==[dict(start=0,end=80000,reason='maximum')]
 assert len(seg['test11',policy])==2
assert [r['end'] for r in seg['test7','anchored']]==[79680,80000,83200]
assert [r['end'] for r in seg['test7','baseline']]==[79680,83200]
# phase0 current baseline must reproduce previous product boundaries exactly.
previous=defaultdict(list)
for l in (B/'product.tsv').read_text().splitlines():
 x=l.split('\t')
 if x[0]=='segment' and x[2]=='600' and not x[1].startswith('test'):previous[x[1]].append((int(x[3]),int(x[4])))
for name,rows in previous.items():assert [(r['start'],r['end']) for r in seg[name+'@0','baseline']]==rows
cues=cue_times(Path('/home/hyh/Downloads/opencaption/clip_gold_bilingual.srt').read_text());assert len(cues)==29
q=lambda a,p:sorted(a)[math.ceil(len(a)*p)-1]
s=dict(new_model_requests=0,synthetic_cases_passed=12,phase0_baseline_matches_previous=True,events_causal=True,traces={},phase_metrics={},cue_rows={},queue_grid=[])
for t in m['traces']:
 name=t['name'];s['traces'][name]={}
 for policy in ['baseline','anchored']:
  rows=seg[name,policy];assert rows[0]['start']==0 and rows[-1]['end']==t['samples'];assert all(a['end']==b['start'] for a,b in zip(rows,rows[1:]));assert all(0<r['end']-r['start']<=80000 for r in rows)
  durations=[(r['end']-r['start'])/16 for r in rows]
  s['traces'][name][policy]=dict(requests=len(rows),short_under2s=sum(d<2000 for d in durations),min_ms=min(durations),P50_length_ms=statistics.median(durations),P95_length_ms=q(durations,.95),ownership_complete=True)
 if t['source']!='clip':continue
 phase=t['padding_ms'];shifted=[(a+phase,b+phase) for a,b in cues];s['phase_metrics'][phase]={};s['cue_rows'][phase]={}
 for policy in ['baseline','anchored']:
  rows=seg[name,policy];cr=[]
  for i,(a,b) in enumerate(shifted):
   w=next(r for r in rows if r['start']<=b*16-1<r['end']);cr.append(dict(cue=i+1,end_ms=b,submission_ms=w['end']/16,wait_ms=w['end']/16-b,crossed_boundaries=sum(a*16<r['end']<b*16 for r in rows)))
  s['cue_rows'][phase][policy]=cr;wait=[r['wait_ms'] for r in cr];s['phase_metrics'][phase][policy]=dict(P50_ms=statistics.median(wait),P95_ms=q(wait,.95),crossed_boundaries=sum(r['crossed_boundaries'] for r in cr),n=29)
  for cost in [1000,2000,3000,4000]:
   rs=queue[name,policy,cost];ordered=sorted(rs,key=lambda r:r['start']);assert ordered[0]['start']==0 and ordered[-1]['end']==t['samples']//16;assert all(a['end']==b['start'] for a,b in zip(ordered,ordered[1:]));drops=[r for r in rs if r['state']!='delivered']
   s['queue_grid'].append(dict(phase=phase,policy=policy,service_ms=cost,dropped_ms=sum(r['end']-r['start'] for r in drops),fully_eligible=sum(not any(r['start']<b and r['end']>a for r in drops) for a,b in shifted),n=29,simulated=True))
fails=[];b=s['phase_metrics'][0]['baseline'];c=s['phase_metrics'][0]['anchored'];delta=b['P50_ms']-c['P50_ms']
if delta<200 or delta/b['P50_ms']<.2:fails.append('original_phase_P50_target')
for phase,v in s['phase_metrics'].items():
 if v['anchored']['P95_ms']>v['baseline']['P95_ms']:fails.append(f'phase{phase}_P95_regression')
 if phase and v['anchored']['P50_ms']>v['baseline']['P50_ms']:fails.append(f'phase{phase}_P50_regression')
for name,v in s['traces'].items():
 v['request_growth_percent']=(v['anchored']['requests']/v['baseline']['requests']-1)*100
 if v['request_growth_percent']>25:fails.append(name+'_request_growth')
for phase in s['phase_metrics']:
 for cost in [1000,2000,3000,4000]:
  a=next(r for r in s['queue_grid'] if r['phase']==phase and r['service_ms']==cost and r['policy']=='baseline');c=next(r for r in s['queue_grid'] if r['phase']==phase and r['service_ms']==cost and r['policy']=='anchored')
  if c['dropped_ms']>a['dropped_ms'] or c['fully_eligible']<a['fully_eligible']:fails.append(f'phase{phase}_cost{cost}_load_coverage')
s['gate']=dict(passed=not fails,failure_reasons=fails,original_P50_reduction_ms=delta,original_P50_reduction_percent=delta/b['P50_ms']*100)
s['independent_materials']=False;s['content_quality_tested']=False;s['real_caption_E2E_tested']=False
(O/'summary.json').write_text(json.dumps(s,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in s.items() if k not in ['cue_rows','queue_grid']},ensure_ascii=False,indent=2))
