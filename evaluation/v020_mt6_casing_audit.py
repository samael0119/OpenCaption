"""AI-assisted paired whole-meaning audit, never independent human gold."""
import json,hashlib,statistics,random,math,sys
from pathlib import Path
from v020_semantic_rating_cache import frozen_judgment,raw_digest
ROOT=Path(__file__).resolve().parents[1];B=ROOT/'evaluation/results/v020-mt6';O=B/'casing2'
def read(p):return json.loads(p.read_text())
m=read(O/'manifest.json');allrows={};upper={};low={}
for n in range(4):
 for r in map(json.loads,(B/f'batch{n}.jsonl').read_text().splitlines()):
  if r['type']=='request':upper[r['case_id']]=r
for n in range(3):
 rs=list(map(json.loads,(O/f'batch{n}.jsonl').read_text().splitlines()));assert rs[-1]['type']=='engine_closed';assert any(r['type']=='complete' for r in rs);allrows[n]=rs
 for r in rs:
  if r['type']=='request':low[r['case_id']]=r
# Whole-sentence judgments anchored to unchanged units. Existing exact outputs reuse
# previous whole-sentence ratings; other values are explicit AI-assisted audit.
sets={
 'E2B_text':{'whisper-'+str(x) for x in [461,464,466,471,474,475,476,478]}|{'1272-128104-0014','1272-135031-0003','1272-135031-0005','1272-135031-0008','1272-135031-0009'},
 'MT_upper':{'whisper-'+str(x) for x in [461,464,471,475,476]}|{'1272-128104-0014','1272-135031-0008','1272-135031-0009','1272-135031-0012'},
 'MT_lower':{'whisper-'+str(x) for x in [461,462,464,466,471,475,476,478]}|{'1272-135031-0009'}}
reasons={
 '1272-128104-0001':'Lower reverses/weakens no-less comparison; old E2B awkward comparison conservative false retained.',
 '1272-128104-0014':'Lower M A becomes 马 (credential lost/name extended); upper literal M A accepted.',
 '1272-135031-0003':'Lower raps=饶舌声 and upper鼠标 replace knocks; E2B preserves knocks.',
 '1272-135031-0004':'Lower escaped disgrace rather than fled in disgrace; asking-for repaired only partially.',
 '1272-135031-0005':'Lower omits Ruggedo; upper begged/long-ago damaged. Existing E2B did-not-do accepted unchanged.',
 '1272-135031-0006':'Lower adds older-brother and offered becomes promised; old E2B unwillingness uncertainty false retained.',
 '1272-135031-0007':'Lower changes action/speaker relation; E2B adds drinking; upper reply relation wrong.',
 '1272-135031-0008':'Lower Shaggy becomes 说废话, loses identity; upper and E2B named attribution accepted.',
 '1272-135031-0009':'All preserve negation/no working; no extra fact required for sense.',
 '1272-135031-0011':'All returned interpreted as physical return rather than dialogue attribution.',
 '1272-135031-0012':'Lower adds younger/upper preserves generic brother/E2B adds older; unchanged original audio correct.',
 '1272-135031-0013':'Lower asks 毛毛 vs Shaggy as inquirer; role/name ambiguous. Previous E2B false retained.',
 'whisper-462':'Old frozen conjunction error retained for E2B; upper wrong action; lower desk faithful to audio but drops ASR conjunction.',
 'whisper-474':'Lower 承认 is wrong/uncertain for recognition command; uncertainty not correct; upper声明 also wrong.',
 'whisper-468':'Lower private-use/garbled output; E2B and upper faithful to misrecognized hope, still wrong for open.',
 'whisper-469':'Lower removes reassuring future claim but repeats sickness; still wrong for music; source fidelity is separate.'}
old=read(ROOT/'evaluation/results/v020-hybrid/candidate2_chinese_review.json')['rows'];cache=[]
for c in m['cases']:
 for r in old:
  if r['case_id']!=c['id']:continue
  for prefix in ['baseline','candidate2']:
   cache.append(dict(case_id=c['id'],raw_sha256=r[prefix+'_sha256'],actual_raw=r[prefix+'_raw'],semantic_units=c['semantic_units'],english_ratings=[],chinese_ratings=['preserved' if r[prefix+'_complete'] else 'omitted']))
rows=[]
for c in m['cases']:
 key=c['id'];raws={'E2B_text':c['baseline_text_translation'],'MT_upper':upper[key]['raw'],'MT_lower':low[key]['raw']};scores={};provenance={}
 for arm,raw in raws.items():
  frozen=frozen_judgment(key,raw,c['semantic_units'],cache)
  val=key in sets[arm]
  if frozen is not None:
   if (frozen['zh']==['preserved'])!=val:raise ValueError('Old whole rating conflict '+key)
   provenance[arm]=frozen['provenance']
  else:provenance[arm]='new_AI_assisted_development_whole_sentence_audit'
  scores[arm]=val
 rows.append(dict(case_id=key,group=c['group'],reference_en=c['reference_en'],semantic_units=c['semantic_units'],original_ASR=c['original_input_text'],normalized_ASR=c['input_text'],raws=raws,raw_sha256={k:raw_digest(v) for k,v in raws.items()},complete=scores,rating_provenance=provenance,original_audio_baseline=c['baseline_audio_translation'],note=reasons.get(key,'Frozen command sense; synonyms allowed; ASR errors cannot count as repaired by merely faithful MT.')))
# Deterministic percentile bootstrap paired difference; descriptive development only.
def paired(a,b,items):
 ds=[int(r['complete'][b])-int(r['complete'][a]) for r in items];n=len(ds);rng=random.Random(20261015)
 boots=sorted(sum(rng.choice(ds) for _ in range(n))/n*100 for _ in range(10000))
 return dict(n=n,baseline_correct=sum(r['complete'][a] for r in items),candidate_correct=sum(r['complete'][b] for r in items),repairs=ds.count(1),losses=ds.count(-1),net=sum(ds),delta_pp=sum(ds)/n*100,paired_bootstrap95_pp=[boots[249],boots[9749]],independent_confirmation=False)
def quant(xs,p):return sorted(xs)[math.ceil(p*len(xs))-1]
summary={'actual_new_requests':30,'actual_total_requests':501,'logical_control_cache_replays':6,'not_independent_human_gold':True,'groups':{},'candidate2_rejected':True,'P2_P3_triggered':False}
for group in ['all','natural_whisper','ordinary']:
 rs=rows if group=='all' else [r for r in rows if r['group']==group]
 summary['groups'][group]={'E2B_to_lower':paired('E2B_text','MT_lower',rs),'upper_to_lower':paired('MT_upper','MT_lower',rs)}
 summary['groups'][group]['correct_three_arms']={a:sum(r['complete'][a] for r in rs) for a in sets}
ms=[r['decode_ms'] for r in low.values()];loads=[r['load_ms'] for rs in allrows.values() for r in rs if r['type']=='engine_initialized'];closes=[r['close_ms'] for rs in allrows.values() for r in rs if r['type']=='engine_closed']
summary['resource']={'load_median_ms':statistics.median(loads),'decode_P50_ms':statistics.median(ms),'decode_P95_nearest_rank_ms':quant(ms,.95),'close_median_ms':statistics.median(closes),'peak_cgroup_bytes':max(int(r['resources']['memory.peak']) for rs in allrows.values() for r in rs if r['type']=='complete'),'nonempty':sum(bool(r['raw']) for r in low.values()),'possible_truncation':sum(r['possibly_truncated'] for r in low.values()),'real_caption_E2E_measured':False}
summary['new_critical_defects_vs_E2B_text']=[{'case_id':k,'defect':v} for k,v in [
('1272-128104-0014','M A credential lost/replaced by 马'),('1272-135031-0003','knocks replaced with rapping'),('1272-135031-0005','Ruggedo identity omitted'),('1272-135031-0008','Shaggy identity replaced by 说废话'),('1272-135031-0012','unspecified brother becomes younger'),('whisper-468','previous readable translation becomes garbled')]]
summary['critical_errors_not_all_new_whole_failures']=True
summary['sensitivity']='Changing both legacy willingness cases symmetrically cannot repair M A/knocking/names losses; primary labels unchanged. No P2 decision depends on re-rating them.'
summary['unchanged_fallback_six']='Original E2B audio retained; 0 new inference, excluded from MT30 denominator. No acoustic coverage benefit claimed.'
(O/'semantic_audit.json').write_text(json.dumps(dict(kind='AI_assisted_development_not_independent_human_gold',rows=rows),ensure_ascii=False,indent=2)+'\n')
(O/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps(summary,ensure_ascii=False,indent=2))
