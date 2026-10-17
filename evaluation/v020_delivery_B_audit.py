"""Post-run delivery audit; all SRT-based numbers remain development proxies."""
import json,hashlib,statistics,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1];O=R/'evaluation/results/v020-delivery/B';D=O/'live'
def rows(p):return [json.loads(l) for l in p.read_text().splitlines()]
def merge(ranges):
 result=[]
 for a,b in sorted(ranges):
  assert b>a
  if result and a<result[-1][1]:raise AssertionError(('overlap',a,b,result[-1]))
  if result and a==result[-1][1]:result[-1][1]=b
  else:result.append([a,b])
 return result
def main():
 r=rows(D/'run.jsonl');u=rows(D/'ui.jsonl');m=json.loads((O/'prepare_manifest.json').read_text());ref=json.loads((O/'reference_proxy.json').read_text())
 assert r[-1]['type']=='complete' and not any(v['type']=='failure' for v in r)
 result=[v for v in r if v['type']=='result'];started=[v for v in r if v['type']=='started'];assert len(result)==len(started)==r[-1]['requests']<=54
 assert not (D/'browser_errors.jsonl').exists()
 batches=[];visual={};clocks={}
 for b,item in enumerate(m['order']):
  rr=[v for v in r if v.get('batch')==b];res=[v for v in result if v['batch']==b]
  assert len(res)<=item['max_requests'] and any(v['type']=='batch_complete' for v in rr)
  offered=[v['fields'] for v in rr if v['type']=='capture_event' and v['kind']=='OFFER'];ranges=[(int(f[1]),int(f[2])) for f in offered];assert merge(ranges)==[[0,30000]]
  expected=m['pieces'][item['piece']]['boundaries'][item['strategy']]
  assert ranges==[(x['start_sample']//16,x['end_sample']//16) for x in expected]
  clock=next(v for v in rr if v['type']=='clock_calibration');lo=clock['python_begin_before_ms'];hi=clock['python_clock_received_ms']-clock['java_clock_ms'];assert hi>=lo;clocks[b]=(lo,hi)
  gaps=[(int(v['fields'][1]),int(v['fields'][2])) for v in rr if v['type']=='capture_event' and v['kind']=='GAP']
  zero=[(int(v['fields'][1]),int(v['fields'][2])) for v in rr if v['type']=='capture_event' and v['kind']=='ZERO']
  assert merge([(v['start_ms'],v['end_ms']) for v in res]+gaps+zero)==[[0,30000]]
  ack={v['event_id']:v for v in rr if v['type']=='model_ack_sent'};eligible=0;dur=[]
  for v in res:
   dur.append(v['inference_ms'])
   if v['status']!='subtitle':continue
   candidates=[x for x in u if x.get('event_id')==v['event_id'] and x['type']=='browser_frame_bound' and x.get('fully_in_viewport') and x['visibility']=='visible']
   if candidates:
    first=min(candidates,key=lambda x:x['browser_ms']);assert ack[v['event_id']]['server_received_ms']<first['server_received_ms'];visual[v['event_id']]=first;eligible+=1
  batches.append(dict(batch=b,**{k:item[k] for k in ['piece','strategy']},requests=len(res),subtitle=sum(v['status']=='subtitle' for v in res),invalid=sum(v['status']=='invalid' for v in res),no_speech=sum(v['status']=='no_speech' for v in res),queue_gap_ms=sum(z-a for a,z in gaps),zero_filtered_ms=sum(z-a for a,z in zero),full_chinese_layout_observed=eligible,java_clock_origin_width_ms=hi-lo,service_median_ms=statistics.median(dur) if dur else None))
 # All 29 proxy units are retained. Cross-piece units remain explicitly unmappable.
 proxies=[]
 for unit in ref['items']:
  row={'id':unit['id'],'crosses_artificial_boundary':unit['crosses_artificial_boundary'],'reference_provenance':ref['classification'],'semantic_correctness':'not_independently_rated'}
  for strategy in ['fixed','pause']:
   matches=[]
   if not unit['crosses_artificial_boundary']:
    for v in result:
     if v['strategy']!=strategy or not (v['absolute_start_ms']<unit['end_ms']<=v['absolute_end_ms']):continue
     frame=visual.get(v['event_id'])
     if frame:
      lo,hi=clocks[v['batch']];end_local=unit['end_ms']-m['pieces'][v['piece']]['absolute_start_ms']
      matches.append({'event_id':v['event_id'],'proxy_min_ms':frame['server_time_min_ms']-hi-end_local,'proxy_max_ms':frame['server_time_max_ms']-lo-end_local,'ui_chinese':frame['caption_chinese']})
   row[strategy]=matches[0] if matches else None
  proxies.append(row)
 paired=[v for v in proxies if v['fixed'] and v['pause']]
 def mid(v,key):return (v[key]['proxy_min_ms']+v[key]['proxy_max_ms'])/2
 med={k:statistics.median(mid(v,k) for v in paired) if paired else None for k in ['fixed','pause']}
 resource=[v['resources'] for v in r if v.get('resources')]
 for v in resource:
  assert v['memory.max']==str(6*1024**3) and v['memory.swap.max']=='0' and v['memory.swap.current']=='0'
  e=dict(x.split() for x in v['memory.events'].splitlines());assert int(e['oom'])==int(e['oom_kill'])==0
 out={'requests':len(result),'batches':batches,'observed_scope_peak_bytes':max(int(v['memory.peak']) for v in resource),'oom_observed':0,'swap_observed':0,'proxy_units_total':len(proxies),'proxy_units_paired':len(paired),'cross_boundary_units':[v['id'] for v in proxies if v['crosses_artificial_boundary']],'paired_delivery_proxy_median_ms':med,'paired_proxy_p50_improvement_ms':med['fixed']-med['pause'] if paired else None,'paired_proxy_p50_improvement_fraction':1-med['pause']/med['fixed'] if paired and med['fixed'] else None,'p95_reported':False,'p95_reason':'Fewer than 60 eligible independent semantic observations; timestamps and semantic correctness not human-verified','independent_quality_passed':False,'stable_correct_chinese_latency_passed':False,'display':'Xvfb virtual rendering and SRT endpoints; interval-coverage proxy only','inherited_ui_label_note':'preview banner/cache semantic tag are inherited instrumentation labels; live started/result and input hashes identify actual Gemma generation, not cache replay','units':proxies}
 (O/'live_technical_audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in out.items() if k not in ['units','batches']},ensure_ascii=False))
if __name__=='__main__':main()
