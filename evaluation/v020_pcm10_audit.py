"""R10 paired technical audit with exact frozen semantic rating reuse."""
import collections,hashlib,json,statistics
import v020_pcm10 as x
from v020_semantic_rating_cache import frozen_judgment,preserved_count

def quant(v,p):
 a=sorted(v);t=(len(a)-1)*p;i=int(t);return a[i]+(a[min(i+1,len(a)-1)]-a[i])*(t-i)
def norm(s):return ' '.join(__import__('re').findall(r"[a-z0-9]+",s.lower()))
def main():
 m=x.verify();events=[json.loads(l) for l in (x.O/'requests.jsonl').read_text().splitlines()];assert events[-1]['type']=='complete' and events[-1]['requests']==24
 rows=[r for r in events if r['type']=='request'];assert len(rows)==24 and len({r['index'] for r in rows})==24
 d=collections.defaultdict(dict)
 for r in rows:d[str(r['case_id'])][r['mode']]=r
 pool=x.read(x.R/'evaluation/results/v020-round3/candidate1/frozen_ratings.json');pairs=[]
 for c in m['cases']:
  p=dict(case_id=c['id'],group=c['group'],reference_en=c.get('reference_en'),semantic_units=c.get('semantic_units'),current=d[str(c['id'])]['current'],candidate=d[str(c['id'])]['candidate'])
  p['delivered_equal']=all(p['current'][k]==p['candidate'][k] for k in ['status','english','chinese']);p['raw_equal']=p['current']['raw']==p['candidate']['raw']
  for k in ['current','candidate']:
   r=p[k];r['strict_english']=r['status']=='subtitle' and norm(r['english'])==norm(c.get('reference_en','')) if c['group'] not in ['music','known_short_music'] else None
   if c.get('semantic_units'):r['frozen_semantic']=frozen_judgment(c['id'],r['raw'],c['semantic_units'],pool)
  pairs.append(p)
 result=dict(complete=True,requests=24,pairs=12,delivered_equal=sum(p['delivered_equal'] for p in pairs),raw_equal=sum(p['raw_equal'] for p in pairs),groups={},semantic_review_complete=False,independent=False,new_model_requests=24)
 for g in sorted({p['group'] for p in pairs}):
  ps=[p for p in pairs if p['group']==g];result['groups'][g]={}
  for mode in ['current','candidate']:
   rs=[p[mode] for p in ps];result['groups'][g][mode]=dict(n=len(rs),statuses=dict(collections.Counter(r['status'] for r in rs)),english_strict=sum(r['strict_english'] is True for r in rs),p50=statistics.median(r['inference_ms'] for r in rs))
 result['timing']={mode:dict(p50=statistics.median(r['inference_ms'] for r in rows if r['mode']==mode),p95=quant([r['inference_ms'] for r in rows if r['mode']==mode],.95)) for mode in ['current','candidate']}
 result['without_first_pair']={mode:dict(n=11,p50=statistics.median(r['inference_ms'] for r in rows if r['mode']==mode and str(r['case_id'])!=str(m['cases'][0]['id'])),p95=quant([r['inference_ms'] for r in rows if r['mode']==mode and str(r['case_id'])!=str(m['cases'][0]['id'])],.95)) for mode in ['current','candidate']}
 for name,obj in [('paired_review.json',pairs),('technical_summary.json',result)]:
  with (x.O/name).open('x') as f:json.dump(obj,f,ensure_ascii=False,indent=2)
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
