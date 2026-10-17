"""Explicit AI-assisted review, frozen unit identities, no reference rewrite."""
import json,statistics,hashlib
from pathlib import Path
from v020_semantic_rating_cache import frozen_judgment,raw_digest
O=Path('evaluation/results/v020-diagnostic11')
def save(n,x):(O/n).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
P='preserved';C='contradicted';U='uncertain';M='omitted'
RATINGS={1860:([C,M,P],[C,M,P]),1870:([P,P],[P,P]),1889:([P,P],[P,P]),
1908:([P,P],[P,U]),1941:([P,P,P],[P,P,P]),1957:([P,P,P],[P,P,P]),
1972:([C,P,P],[C,P,P]),1978:([P,P,P],[C,P,P])}
REASONS={1860:'Said injured subset replaced with appointed intrastate police;19 retained, statement/action and injury relation lost.',
1870:'Both displayed scenes and illuminated pyramids retained; no invented scene details.',
1889:'Train,car and other transport retained; unspecified it not expanded.',
1908:'English matches;Chinese nouns differs from objects, but isolated source sense unresolved. Keep unit2 uncertain, outside primary6.',
1941:'Couples,may choose and baby adoption plan retained; no imposed adoption direction.',
1957:'Current product parser accepts unlabeled bilingual raw. It preserves attributed political chatter/silliness; do not count formatting failure.',
1972:'Many people/them replaced by my people/us (Chinese my ethnicity/us);feathers and flight retained. Changed agents make whole sentence fail.',
1978:'English faithful;Chinese Spring bears is unsupported team identity. Ended five losses retained, which conflicts with publisher Chinese. Diagnostic only.'}
def main():
 m=json.loads((O/'manifest.json').read_text());rows=[json.loads(l) for l in (O/'requests.jsonl').read_text().splitlines()]
 req=[r for r in rows if r['type']=='request'];starts=[r for r in rows if r['type']=='started'];assert len(req)==len(starts)==16 and rows[-1]['type']=='complete'
 assert [{k:r[k] for k in ('index','case_id','mode')} for r in req]==m['order']
 # Check every frozen dependency and real input, without changing original manifest.
 for p,h in m['files'].items():assert hashlib.sha256(Path(p).read_bytes()).hexdigest()==h,p
 cases={c['id']:c for c in m['cases']};records=[];pairs=[]
 old=json.loads(Path('evaluation/results/v020-round3/candidate1/frozen_ratings.json').read_text())
 if isinstance(old,dict):old=old.get('records',old.get('ratings',[]))
 for cid,c in cases.items():
  a=next(r for r in req if r['case_id']==cid and r['mode']=='audio');b=next(r for r in req if r['case_id']==cid and r['mode']=='text_reference')
  en,zh=RATINGS[cid];cached=frozen_judgment(cid,a['raw'],c['semantic_units'],old)
  if cached:assert cached['en']==en and cached['zh']==zh
  text_zh=[P]*len(en)
  if cid==1978:text_zh=[U,P,P]
  for raw,er,zr,mode in [(a['raw'],en,zh,'audio'),(b['raw'],[P]*len(en),text_zh,'text_reference')]:
   records.append(dict(case_id=cid,mode=mode,actual_raw=raw,raw_sha256=raw_digest(raw),semantic_units=c['semantic_units'],english_ratings=er,chinese_ratings=zr,provenance='AI-assisted explicit review,not independent human; text English is supplied reference,not ASR',reason=REASONS[cid] if mode=='audio' else 'Supplied English reference text, Chinese meaning retained;Springboks transliteration uncertain in1978'))
  pairs.append(dict(case_id=cid,primary=c['primary'],audio_status=a['status'],audio_english=en,audio_chinese=zh,text_chinese=text_zh,reason=REASONS[cid],raw_audio=a['raw'],raw_text=b['raw']))
 primary=[p for p in pairs if p['primary']]
 lost=[(p['case_id'],i) for p in primary for i,(en,zh) in enumerate(zip(p['audio_english'],p['audio_chinese'])) if en!=P and zh!=P]
 only_zh=[(p['case_id'],i) for p in primary for i,(en,zh) in enumerate(zip(p['audio_english'],p['audio_chinese'])) if en==P and zh!=P]
 summary=dict(requests=16,primary_cases=6,total_cases=8,primary_units=16,
   audio_en_units=sum(x==P for p in primary for x in p['audio_english']),audio_zh_units=sum(x==P for p in primary for x in p['audio_chinese']),
   text_zh_units=sum(x==P for p in primary for x in p['text_chinese']),
   audio_zh_whole=sum(all(x==P for x in p['audio_chinese']) for p in primary),text_zh_whole=sum(all(x==P for x in p['text_chinese']) for p in primary),
   audio_format_coverage=sum(p['audio_status']=='subtitle' for p in pairs),audio_format_denominator=8,
   en_and_zh_shared_loss=lost,en_correct_zh_loss=only_zh,shared_loss_case_count=len(set(c for c,i in lost)),
   main_text_loss_units=0,ambiguous_cases=[1908],reference_conflict_cases=[1978],
   thresholds_do_not_trigger_product_candidate=True,AI_assisted_not_independent=True,
   audio_service_median_ms=statistics.median(r['inference_ms'] for r in req if r['mode']=='audio'),
   text_service_median_ms=statistics.median(r['inference_ms'] for r in req if r['mode']=='text_reference'),
   timings_not_causal_or_E2E=True,resources=rows[-1]['resources'])
 save('semantic_review.json',dict(records=records,pairs=pairs,prior_ratings_unchanged=True));save('summary.json',summary)
 print(json.dumps(summary,ensure_ascii=False))
if __name__=='__main__':main()
