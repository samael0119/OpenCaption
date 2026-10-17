"""One bounded, offline inventory. Does not extract archives or run ASR."""
import hashlib,json,wave
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evaluation/results/v020-delivery/A'
SOURCES={
 'local':Path('/home/hyh/Downloads/opencaption'),
 'controls':ROOT/'evaluation/results/v020-independent/assets',
 'fleurs_old':ROOT/'evaluation/results/v020-independent/fleurs_preflight/audio',
 'fleurs_observed11':ROOT/'evaluation/results/v020-evidence11/audio',
}
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 target=OUT/'inventory.json'
 if target.exists():raise RuntimeError('Inventory already saved: reuse, do not silently rescan')
 old=json.loads((ROOT/'evaluation/results/v020-independent/source_inventory.json').read_text())
 observed={x['sha256']:x for x in old['local']}
 rows=[];reference_files=[]
 for group,d in SOURCES.items():
  paths=sorted(d.iterdir()) if d.exists() else []
  if len(paths)>500:raise RuntimeError('bounded directory inventory exceeded')
  for p in paths:
   if not p.is_file():continue
   if p.suffix.lower() in ('.srt','.txt','.tsv'):reference_files.append(str(p));continue
   if p.suffix.lower() not in ('.wav','.ogg','.parquet'):continue
   r={'group':group,'path':str(p),'bytes':p.stat().st_size,'sha256':sha(p)}
   if p.suffix.lower()=='.wav':
    try:
     with wave.open(str(p)) as w:r.update(seconds=w.getnframes()/w.getframerate(),rate=w.getframerate(),channels=w.getnchannels())
    except wave.Error as e:r['wave_header_limitation']=str(e)
   r.update(independent_confirmation_qualified=False,human_pause_endpoints_available=False)
   if r['sha256'] in observed:r.update(observed=True,role='development',reference=observed[r['sha256']]['reference'])
   elif group.startswith('fleurs'):r.update(observed=True,role='observed_isolated_utterances',reference='publisher parallel text; no verified speaker IDs or natural continuous timestamps')
   else:r.update(observed_or_qualification_unknown=True,role='control_only',reference='English-only speech or non-speech; no paired human Chinese/pause annotation')
   rows.append(r)
 result={'scope':{k:str(v) for k,v in SOURCES.items()},'source_inventory_sha256':sha(ROOT/'evaluation/results/v020-independent/source_inventory.json'),'records':rows,'reference_files':reference_files,'qualified_confirmation_clips':0,'qualified_confirmation_seconds':0,'qualified_independent_source_groups':0,'qualified_human_semantic_units':0,'qualified_pause_endpoints':0,'missing':{'new_natural_continuous_audio_seconds':[360,480],'independent_sources':3,'human_semantic_units':60,'human_pause_endpoints':30,'note':'No qualifying set found in listed bounded locations; not a global claim about all local files or internet availability.'},'review_pack':[{'path':x['path'],'sha256':x['sha256'],'role':'known development only; cannot become independent by relabeling','needed':'For diagnostics only: verify SRT semantic endpoint alignment. Do not use for new-source confirmation.'} for x in old['local']],'network_requests':0,'model_requests':0,'archive_extractions':0,'AI_rating_is_not_human_reference':True}
 target.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(json.dumps({'records':len(rows),'qualified_confirmation_clips':0,'model_requests':0,'report':str(target)},ensure_ascii=False))
if __name__=='__main__':main()
