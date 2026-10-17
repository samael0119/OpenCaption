"""Post-hoc chunk oracle only, never an online finalization rule."""
import collections,json,statistics,time
import v020_stream9 as x

def quant(v,p):
 a=sorted(v);t=(len(a)-1)*p;i=int(t);return a[i]+(a[min(i+1,len(a)-1)]-a[i])*(t-i)
def main():
 m=x.verify();allrows=[json.loads(l) for l in (x.O/'requests.jsonl').read_text().splitlines()];assert allrows[-1]['type']=='complete' and allrows[-1]['requests']==16
 rows=[r for r in allrows if r['type']=='request'];assert len(rows)==16 and len({r['index'] for r in rows})==16
 groups=collections.defaultdict(dict)
 for r in rows:groups[str(r['case_id'])][r['mode']]=r
 b=x.Protocol();pairs=[]
 try:
  for cid,d in groups.items():
   a,s=d['sync'],d['stream'];chunks=[r for r in allrows if r['type']=='chunk' and r['index']==s['index']];hyp=s['hypotheses'];matches=[k for k in ['delta','cumulative'] if hyp[k]==a['raw']];mode=matches[0] if matches else None
   out=dict(case_id=cid,group=a['group'],sync_ms=a['service_ms'],stream_ms=s['service_ms'],sync_raw=a['raw'],hypotheses=hyp,matching_reconstructions=matches,chunk_count=len(chunks),oracle_ms=None,saving_ms=None,saving_fraction=None)
   # If no paired exact match, retain both hypotheses, do not invent a valid final.
   if mode:
    states=[];raw=''
    for c in chunks:
     t=x.text_chunk(c['chunk']);raw=raw+t if mode=='delta' else (t if t else raw);states.append(dict(at=c['at_ms'],raw=raw,parsed=b.parse(raw)))
    final=b.parse(a['raw']);out['final_parsed']=final;out['final_equal']=True
    if final['status']=='subtitle':
     same=[i for i,z in enumerate(states) if z['parsed']==final and all(v['parsed']==final for v in states[i:])]
     if same:
      earliest=states[same[0]]['at'];out.update(oracle_ms=earliest,saving_ms=s['service_ms']-earliest,saving_fraction=(s['service_ms']-earliest)/s['service_ms'])
     visible=[z for z in states if z['parsed']['status']=='subtitle'];out['first_readable_ms']=visible[0]['at'] if visible else None
     # Full-current parsed preview growth is not a committed/history revision.
     out['partial_preview_changes']=sum(u['parsed']['chinese']!=v['parsed']['chinese'] for u,v in zip(visible,visible[1:]));out['first_readable_is_final']=bool(visible and visible[0]['parsed']==final)
    out['states']=states
   else:out['final_equal']=False
   pairs.append(out)
 finally:b.close()
 voiced=[p for p in pairs if p['group'] not in ['music','known_short_music']];savings=[p['saving_ms'] for p in voiced if p['saving_ms'] is not None];fractions=[p['saving_fraction'] for p in voiced if p['saving_fraction'] is not None]
 summary=dict(complete=True,requests=16,pairs=8,exact_pairs=sum(p['final_equal'] for p in pairs),voiced_n=6,oracle_measurable=len(savings),oracle_saving_p50_ms=statistics.median(savings) if savings else None,oracle_fraction_p50=statistics.median(fractions) if fractions else None,service_p50_ms={k:statistics.median([r['service_ms'] for r in rows if r['mode']==k]) for k in ['sync','stream']},service_p95_ms={k:quant([r['service_ms'] for r in rows if r['mode']==k],.95) for k in ['sync','stream']},oracle_not_online=True,not_screen_E2E=True,SDK_errors_cancellation_native_integration_tested=False)
 summary['gate_passed']=summary['exact_pairs']==8 and len(savings)==6 and statistics.median(savings)>=200 and statistics.median(fractions)>=.2 and summary['service_p95_ms']['stream']<=summary['service_p95_ms']['sync']*1.05
 x.put(x.O/'paired_audit.json',pairs);x.put(x.O/'summary.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
