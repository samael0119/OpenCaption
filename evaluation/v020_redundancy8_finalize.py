"""Final rejection: compare deterministic guards; never invent missing scores."""
import collections,datetime,hashlib,json,pathlib
from v020_semantic_rating_cache import frozen_judgment,preserved_count
R=pathlib.Path(__file__).resolve().parents[1];O=R/'evaluation/results/v020-redundancy8'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
m=json.loads((O/'manifest.json').read_text());s=json.loads((O/'component_summary.json').read_text());assert s['n_pairs']==41 and s['new_model_requests']==82
rows=[r for r in map(json.loads,(O/'requests.jsonl').read_text().splitlines()) if r['type']=='request'];cs={str(c['id']):c for c in m['cases']}
old=json.loads((R/'evaluation/results/v020-round3/candidate1/frozen_ratings.json').read_text());judgments=[];scores=collections.Counter();old_same=0
for r in rows:
 c=cs[str(r['case_id'])]
 # Explicit SHA comparison, without case-name-blind reuse of judgments.
 if r['mode']=='baseline' and hashlib.sha256(r['raw'].encode()).hexdigest()==c['old_baseline_raw_sha256']:old_same+=1
 if c['group']!='fleurs_semantic':continue
 j=frozen_judgment(c['id'],r['raw'],c['semantic_units'],old)
 judgments.append(dict(case_id=c['id'],mode=r['mode'],raw_sha256=hashlib.sha256(r['raw'].encode()).hexdigest(),semantic_units=c['semantic_units'],judgment=j,provenance='frozen_exact_raw_reuse' if j else 'unrated_not_counted_as_correct'))
 if j:
  scores[r['mode']+'_rated_cases']+=1;scores[r['mode']+'_zh_preserved']+=preserved_count(j['zh']);scores[r['mode']+'_units_rated']+=len(j['zh'])
 else:scores[r['mode']+'_unrated_cases']+=1
(O/'semantic_cache_audit.json').write_text(json.dumps(dict(records=judgments,counts=dict(scores),old_baseline_raw_exact_match=old_same,whole_candidate_Chinese_accuracy_measured=False,independent_human=False,note='Already rejected by latency/coverage; do not re-rate unchanged raw or invent whole-sentence Chinese scores. Source English metrics stay separate.'),ensure_ascii=False,indent=2)+'\n')
source=json.loads((R/'evaluation/results/v020-round2/scene-denial/source_snapshot.json').read_text());diff=[p for p,h in source['files'].items() if not (R/p).exists() or sha(R/p)!=h];assert not diff,diff
# Check all original frozen dependencies after execution, including SDK and current bridge.
for p,h in m['files'].items():assert sha(pathlib.Path(p) if p.startswith('/') else R/p)==h,p
coverage_nonregression=all(v['candidate']>=v['baseline'] for g,v in s['coverage'].items() if g not in ['music','known_short_music'])
gates=dict(redundant_count_reduction_80=s['gains']['redundant_count_reduction']>=.8,redundant_char_reduction_80=s['gains']['redundant_char_reduction']>=.8,p50_improvement_20=s['gains']['p50_improvement']>=.2,p95_nonregression_5=s['gains']['p95_change']<=.05,coverage_nonregression=coverage_nonregression)
verdict=dict(accepted=False,gates=gates,reason='Duplicate occurrence reduction75% below80%; P50 slower1.63%, voiced format coverage36->35; ordinary English strict5->4. No second wording/confirmation/integration.',scoring=dict(whole_Chinese_not_measured=True,no_old_rating_changes=True,critical_error_guard_not_fully_rated=True),reused_cached_judgments=dict(scores),baseline_raw_same_as_old=old_same,product_files_checked=len(source['files']),product_changes=diff,new_requests=82,total_calls=583,engineering_load_attempts=2,actual_inference_residencies=1,OOM=0,swap_current=0,real_E2E_measured=False,component_only=True,independent_confirmation_triggered=False,at=datetime.datetime.now().astimezone().isoformat())
(O/'verdict.json').write_text(json.dumps(verdict,ensure_ascii=False,indent=2)+'\n');print(json.dumps(verdict,ensure_ascii=False,indent=2))
