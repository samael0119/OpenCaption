"""Post-run mechanism/component audit, never labels timing as screen E2E."""
import collections,hashlib,json,math,pathlib,random,statistics,sys
import v020_integrity8 as parser
from score_reference import words,edit_distance
R=pathlib.Path(__file__).resolve().parents[1];O=R/'evaluation/results/v020-redundancy8'
def q(v,p):
 v=sorted(v);i=(len(v)-1)*p;a=int(i);return v[a]+(v[min(a+1,len(v)-1)]-v[a])*(i-a)
def stats(v):return dict(n=len(v),p50=statistics.median(v),p95=q(v,.95),mean=statistics.mean(v))
def main():
 allrows=[json.loads(l) for l in (O/'requests.jsonl').read_text().splitlines()];assert allrows[-1]['type']=='complete'
 rows=[r for r in allrows if r['type']=='request'];assert len(rows)==82
 m=json.loads((O/'manifest.json').read_text());cases={str(c['id']):c for c in m['cases']};original=json.loads((parser.O/'manifest.json').read_text())
 src='android/app/src/main/kotlin/dev/opencaption/opencaption/E2eProtocol.kt';assert hashlib.sha256((R/src).read_bytes()).hexdigest()==original['files'][src]
 b=parser.Bridge();repeat=collections.Counter();redundant_chars=collections.Counter();details=[]
 try:
  for r in rows:
   p,cleaned,pairs=b.call('bilingual',r['raw']);assert p=={k:r[k] for k in ['status','english','chinese','reason']}
   pre=cleaned[:pairs[0]['start']] if pairs else '';norm=lambda s:' '.join(s.strip().split())
   redundant=bool(pairs and pre.strip() and norm(pre) in [norm(pairs[0]['english']),norm(pairs[0]['english']+'\n'+pairs[0]['chinese'])])
   if redundant:repeat[r['mode']]+=1;redundant_chars[r['mode']]+=len(pre)
   details.append(dict(r,redundant_prefix=redundant,prefix_characters=len(pre) if redundant else 0))
 finally:b.close()
 by_case=collections.defaultdict(dict)
 for r in details:by_case[str(r['case_id'])][r['mode']]=r
 timing={mode:stats([r['inference_ms'] for r in rows if r['mode']==mode]) for mode in ['baseline','candidate']}
 groups={}
 for group in sorted({r['group'] for r in rows}):
  groups[group]={mode:stats([r['inference_ms'] for r in rows if r['group']==group and r['mode']==mode]) for mode in timing}
 changes=[];source={};cover={};music={};equivalent=0
 for cid,pair in by_case.items():
  a,c=pair['baseline'],pair['candidate'];case=cases[cid]
  if (a['status'],a['english'],a['chinese'])==(c['status'],c['english'],c['chinese']):equivalent+=1
  else:changes.append(dict(case_id=case['id'],group=case['group'],reference_en=case['reference_en'],reference_zh=case.get('reference_zh'),baseline=dict(english=a['english'],chinese=a['chinese'],status=a['status'],raw=a['raw']),candidate=dict(english=c['english'],chinese=c['chinese'],status=c['status'],raw=c['raw'])))
 for group in sorted(groups):
  cover[group]={mode:sum(r['status']=='subtitle' for r in rows if r['group']==group and r['mode']==mode) for mode in timing}
  relevant=[case for case in cases.values() if case['group']==group and case['reference_en']]
  if relevant:
   source[group]={}
   for mode in timing:
    ref=[words(c['reference_en']) for c in relevant];hyp=[words(by_case[str(c['id'])][mode]['english']) for c in relevant]
    err=sum(edit_distance(a,b) for a,b in zip(ref,hyp));n=sum(map(len,ref))
    source[group][mode]=dict(wer_errors=err,reference_words=n,wer=err/n,strict_correct=sum(a==b for a,b in zip(ref,hyp)),n=len(ref))
 for mode in timing:music[mode]=sum(r['status']=='subtitle' for r in rows if r['group'] in ['music','known_short_music'] and r['mode']==mode)
 # Paired case bootstrap, descriptive old developer material only.
 rng=random.Random(820261016);pairs=list(by_case.values());diffs=[]
 for _ in range(5000):
  s=[rng.choice(pairs) for _ in pairs];diffs.append(statistics.median(p['candidate']['inference_ms'] for p in s)-statistics.median(p['baseline']['inference_ms'] for p in s))
 cold=[p for k,p in by_case.items() if str(k)!=str(rows[0]['case_id'])]
 coldstats={mode:stats([p[mode]['inference_ms'] for p in cold]) for mode in timing}
 gains=dict(redundant_count_reduction=1-repeat['candidate']/repeat['baseline'] if repeat['baseline'] else None,redundant_char_reduction=1-redundant_chars['candidate']/redundant_chars['baseline'] if redundant_chars['baseline'] else None,p50_improvement=1-timing['candidate']['p50']/timing['baseline']['p50'],p95_change=timing['candidate']['p95']/timing['baseline']['p95']-1)
 summary=dict(complete=True,n_pairs=41,new_model_requests=82,prior_optimization_calls=501,actual_total=583,redundant_counts=dict(repeat),redundant_chars=dict(redundant_chars),timing=timing,groups=groups,gains=gains,paired_bootstrap_median_delta_ms_95=[q(diffs,.025),q(diffs,.975)],without_first_pair_sensitivity=coldstats,coverage=cover,music_subtitles=music,english_reference=source,identical_delivered_pairs=equivalent,changed_pairs=len(changes),semantic_review_pending=True,independent_gold=False,screen_E2E_measured=False,model_load_attempts=2,actual_audio_inference_residencies=1,engineering_aborted_zero_call_loads=1,last_resources=allrows[-1]['resources'])
 (O/'component_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');(O/'delivered_changes.json').write_text(json.dumps(changes,ensure_ascii=False,indent=2)+'\n')
 with (O/'audited_rows.jsonl').open('x') as f:
  for row in details:f.write(json.dumps(row,ensure_ascii=False)+'\n')
 print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
