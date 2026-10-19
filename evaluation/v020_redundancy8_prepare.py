"""Zero model preparation; frozen case provenance and output overhead only."""
import collections,datetime,hashlib,json,pathlib
R=pathlib.Path(__file__).resolve().parents[1];O=R/'evaluation/results/v020-redundancy8'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def norm(s):return ' '.join(s.strip().split())
def classify(row):
 p=row['ignored_prefix'];pairs=row['pairs']
 if not p.strip() or not pairs:return None
 if norm(p)==norm(pairs[0]['english']):return 'english_echo'
 if norm(p)==norm(pairs[0]['english']+'\n'+pairs[0]['chinese']):return 'pair_echo'
 return None
def metrics(rows):
 repeated=[r for r in rows if classify(r)]
 chars=sum(len(r['raw']) for r in rows);b=sum(len(r['raw'].encode()) for r in rows)
 rc=sum(len(r['ignored_prefix']) for r in repeated);rb=sum(len(r['ignored_prefix'].encode()) for r in repeated)
 return dict(rows=len(rows),repeated=len(repeated),raw_characters=chars,redundant_characters=rc,redundant_character_fraction=rc/chars if chars else 0,raw_utf8_bytes=b,redundant_utf8_bytes=rb,redundant_byte_fraction=rb/b if b else 0)
rows=[json.loads(l) for l in (R/'evaluation/results/v020-integrity8/rows.jsonl').read_text().splitlines()]
u={r['raw_sha256']:r for r in rows};old=R/'evaluation/results/v020-round2/noise1/manifest.json';m=json.loads(old.read_text());req=R/'evaluation/results/v020-round2/noise1/requests.jsonl';base={str(r['case_id']):r for r in map(json.loads,req.read_text().splitlines()) if r.get('type')=='request' and r['mode']=='baseline'}
assert len(base)==len(m['cases'])==41
cases=[];missing=[]
for c in m['cases']:
 assert sha(R/c['path'])==c['sha256']
 r=base[str(c['id'])];h=hashlib.sha256(r['raw'].encode()).hexdigest();cached=u.get(h)
 if cached is None:missing.append(c['id'])
 case={k:v for k,v in c.items() if not k.startswith(('noise_','filtered_')) and k not in ['filter_cli_ms']}
 case.update(old_baseline_raw_sha256=h,old_baseline_raw=r['raw'],old_baseline_inference_ms=r['inference_ms'],old_cached_structure=cached)
 cases.append(case)
assert not missing,missing
selected=[c['old_cached_structure'] for c in cases];stats=dict(complete=True,all_rows=metrics(rows),unique_raw=metrics(list(u.values())),development41=metrics(selected),groups=dict(collections.Counter(c['group'] for c in cases)),token_counts_measured=False,overhead_not_time_or_token=True,missing_cached_raw=missing,new_model_requests=0)
files=['evaluation/results/v020-integrity8/rows.jsonl','evaluation/results/v020-integrity8/manifest.json',str(old.relative_to(R)),str(req.relative_to(R)),'evaluation/v020_redundancy8_prepare.py','docs/dev/archive/v0.2.0第8轮重复生成抑制计划.md']
files.extend(c['path'] for c in cases)
for name,data in [('P0_manifest.json',dict(at=datetime.datetime.now().astimezone().isoformat(),files={p:sha(R/p) for p in files},cases=cases,config=m['config'],model_sha256=m['model_sha256'],prompts=m['prompts'],score_policy=m['scoring'],source_scoring_manifest=str(old.relative_to(R)))),('P0_summary.json',stats)]:
 with (O/name).open('x') as f:json.dump(data,f,ensure_ascii=False,indent=2)
print(json.dumps(stats,ensure_ascii=False,indent=2))
