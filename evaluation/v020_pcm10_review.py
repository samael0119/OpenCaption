"""Explicit AI-assisted judgments for newly observed raws; prior exact cache wins."""
import hashlib,json,random,statistics
import v020_pcm10 as x
from v020_semantic_rating_cache import frozen_judgment,preserved_count

def main():
 pairs=x.read(x.O/'paired_review.json');pool=x.read(x.R/'evaluation/results/v020-round3/candidate1/frozen_ratings.json')
 new={
 1700:dict(en=['omitted','preserved','omitted'],zh=['omitted','preserved','omitted'],reason='Current Chinese 在马里亚之下，在高地之下更厚 preserves thicker under highlands without dinner/eating; thinner under maria still absent. Candidate exact old raw retains old uncertain thicker judgment, not rescored.'),
 1750:dict(en=['preserved','preserved','preserved'],zh=['preserved','preserved','preserved'],reason='Current in birds/鸟类羽毛 explicitly links feathers to birds. Candidate and birds exact old raw omits that relation under frozen rule.'),
 1776:dict(en=['omitted','omitted','preserved','contradicted'],zh=['omitted','omitted','preserved','contradicted'],reason='Current remained/150到200份的副本 does not state made/produced or overnight. Now known preserved; Lenna wrong for Dunlap. Candidate old English contains were made, but old Chinese omits production, scores reused.'),
 1791:dict(en=['omitted','preserved','omitted'],zh=['omitted','preserved','omitted'],reason='Spray painting/scratching and Chinese 喷漆/划痕保留具体动作，但没有禁止或遗址限定，否定作用范围仍丢失。'),
 1792:dict(en=['preserved','preserved','preserved'],zh=['preserved','preserved','preserved'],reason='Current Chinese states pH, making indicator, red cabbage juice; all three same semantic units as cached candidate.')}
 reviews=[]
 for p in pairs:
  if p['group']!='fleurs_semantic':continue
  for mode in ['current','candidate']:
   raw=p[mode]['raw'];r=frozen_judgment(p['case_id'],raw,p['semantic_units'],pool)
   if r is None:
    assert mode=='current' and p['case_id'] in new
    r=dict(new[p['case_id']],provenance='new_explicit_AI_assisted_review_not_independent_human_gold')
   reviews.append(dict(case_id=p['case_id'],mode=mode,actual_raw=raw,raw_sha256=hashlib.sha256(raw.encode()).hexdigest(),semantic_units=p['semantic_units'],**r))
 groups={}
 for mode in ['current','candidate']:
  rs=[r for r in reviews if r['mode']==mode];groups[mode]=dict(n_cases=6,n_units=18,english_preserved=sum(preserved_count(r['en']) for r in rs),chinese_preserved=sum(preserved_count(r['zh']) for r in rs),chinese_complete_cases=sum(all(v=='preserved' for v in r['zh']) for r in rs))
 fixes=losses=0
 for cid in sorted({r['case_id'] for r in reviews}):
  a=next(r for r in reviews if r['case_id']==cid and r['mode']=='current');b=next(r for r in reviews if r['case_id']==cid and r['mode']=='candidate')
  fixes+=sum(u!='preserved' and v=='preserved' for u,v in zip(a['zh'],b['zh']));losses+=sum(u=='preserved' and v!='preserved' for u,v in zip(a['zh'],b['zh']))
 rng=random.Random(1020261016);bs=[];cs=sorted({r['case_id'] for r in reviews})
 for _ in range(5000):
  sampled=rng.choices(cs,k=6);num=den=0
  for cid in sampled:
   a=next(r for r in reviews if r['case_id']==cid and r['mode']=='current');b=next(r for r in reviews if r['case_id']==cid and r['mode']=='candidate');num+=preserved_count(b['zh'])-preserved_count(a['zh']);den+=len(a['zh'])
  bs.append(num/den*100)
 bs.sort();summary=dict(AI_assisted_not_independent=True,groups=groups,chinese_unit_fixes=fixes,chinese_unit_losses=losses,chinese_delta_pp=(groups['candidate']['chinese_preserved']-groups['current']['chinese_preserved'])/18*100,case_block_bootstrap5000_descriptive_interval_pp=[bs[125],bs[4874]],interval_not_independent_population_proof=True)
 verdict=dict(accepted=False,P1_rejected=True,conditional58_triggered=False,independent_triggered=False,new_music_hallucination_cases=1,music_fixed_cases=1,non_speech_hallucinations_both=1,non_speech_denominator=2,reason='Per-case music no-new-hallucination guard fails; AI-assisted Chinese units lose2, no content net benefit. No product integration despite deterministic PCM identity fix.',current_product_baseline_not_old_AudioFile_baseline=True,semantic=summary,product_changed=False)
 for name,obj in [('semantic_review.json',reviews),('semantic_summary.json',summary),('verdict.json',verdict)]:
  with (x.O/name).open('x') as f:json.dump(obj,f,ensure_ascii=False,indent=2)
 print(json.dumps(verdict,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
