"""Validate real transport preflight, explicitly excluding audio/semantic quality."""
import json,hashlib
from pathlib import Path
R=Path(__file__).resolve().parents[1];O=R/'evaluation/results/v020-delivery/B';D=O/'preflight'
def rows(p):return [json.loads(l) for l in p.read_text().splitlines()]
def main():
 r=rows(D/'run.jsonl');u=rows(D/'ui.jsonl');result=[x for x in r if x['type']=='stub_result'];ack={x['event_id']:x for x in r if x['type']=='model_ack_sent'}
 assert len(result)==6 and r[-1]['type']=='complete' and r[-1]['requests']==0 and r[-1]['stub_requests']==6
 assert not any(x['type'] in ['loaded','started','result','failure'] for x in r)
 assert not (D/'browser_errors.jsonl').exists(), 'Browser errors must be reviewed'
 assert [(x['start_ms'],x['end_ms']) for x in result]==[(i*5000,(i+1)*5000) for i in range(6)]
 checks=[]
 for x in result:
  ident=x['event_id'];frames=[v for v in u if v.get('event_id')==ident and v['type']=='browser_frame_bound' and v.get('fully_in_viewport') and v['visibility']=='visible']
  assert frames,(ident,'no fully visible frame')
  assert any(f['caption_chinese']=='本机传输检查。' for f in frames)
  assert ack[ident]['server_received_ms']<min(f['server_received_ms'] for f in frames)
  checks.append({'event_id':ident,'fully_visible_frames':len(frames),'ack_before_frame':True})
 clocks=[v for v in u if v['type']=='clock_sync'];assert len(clocks)>=2 and max(v['max']-v['min'] for v in clocks)<50
 java=[v for v in r if v['type']=='clock_calibration'];assert len(java)==1
 c=java[0];origin_width=c['python_clock_received_ms']-c['java_clock_ms']-c['python_begin_before_ms'];assert 0<=origin_width<50
 resources=[v['resources'] for v in r if v.get('resources')]
 for v in resources:
  assert v['memory.max']==str(3*1024**3) and v['memory.swap.max']=='0' and v['memory.swap.current']=='0'
  e=dict(s.split() for s in v['memory.events'].splitlines());assert int(e['oom'])==int(e['oom_kill'])==0
 assert sum(v['type']=='activity_delivered' for v in u)==30
 out={'passed':True,'runner_manifest_sha256':hashlib.sha256((O/'runner_manifest.json').read_bytes()).hexdigest(),'auditor_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'stub_requests':6,'gemma_requests':0,'activity_events':30,'visible_results':checks,'java_origin_interval_width_ms':origin_width,'maximum_browser_offset_interval_ms':max(v['max']-v['min'] for v in clocks),'scope_peak_bytes':max(int(v['memory.peak']) for v in resources),'oom_observed':0,'swap_observed':0,'independent_quality_or_stable_correct_latency_passed':False}
 (O/'preflight_audit.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out,ensure_ascii=False))
if __name__=='__main__':main()
