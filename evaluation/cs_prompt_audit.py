"""Summarize frozen prompt experiments and explicit nonblind semantic judgments."""
import hashlib,json,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'evaluation/results/cs-prompt-20261021';FULL=OUT/'full';OLD=ROOT/'evaluation/results/cs-domain-20261020/product_round_v2'
def read(p):return json.loads(p.read_text())
def lines(p):return [json.loads(x) for x in p.read_text().splitlines()]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def screen():
 summaries={};allrows=[]
 for sub in [OUT,OUT/'compact',OUT/'final_guards']:
  for r in lines(sub/'screen.jsonl'):
   if r['type']=='result':allrows.append(r)
 for variant in sorted({r['variant'] for r in allrows}):
  rs=[r for r in allrows if r['variant']==variant];cs=[r for r in rs if r['group']=='cs_screen'];music=[r for r in rs if r['group']=='music_guard'];speech=[r for r in rs if r['group']=='speech_guard']
  summaries[variant]=dict(generation_calls=len(rs),cs_windows=len(cs),cs_invalid=sum(r['status']=='invalid' for r in cs),cs_subtitles=sum(r['status']=='subtitle' for r in cs),literal_template_windows=sum('<' in r['raw'] for r in rs),music=dict(windows=len(music),valid_no_speech=sum(r['status']=='no_speech' for r in music),invalid=sum(r['status']=='invalid' for r in music),speech_subtitles=sum(r['status']=='subtitle' for r in music)),ordinary_speech=dict(windows=len(speech),subtitles=sum(r['status']=='subtitle' for r in speech),invalid=sum(r['status']=='invalid' for r in speech),dropped_as_no_speech=sum(r['status']=='no_speech' for r in speech)))
 (OUT/'screen_summary.json').write_text(json.dumps(summaries,ensure_ascii=False,indent=2)+'\n');return summaries

def main():
 screens=screen();rs=lines(FULL/'display.jsonl');refs=read(FULL/'reference.json')['units'];judge=read(FULL/'judgments.json');assert judge['reference_sha256']==sha(FULL/'reference.json');assert judge['display_sha256']==sha(FULL/'display.jsonl');assert len(rs)==59
 previous=read(OLD/'audit.json')['summary'];summary={};js=judge['units']
 for scope in ['primary_match','secondary_interview']:
  us=[u for u in refs if (u['source_id']=='clip_interview_niko')==(scope=='secondary_interview')];chosen=[js[u['id']] for u in us]
  for u,j in zip(us,chosen):
   assert len(j['atoms'])==len(u['atoms']);assert len(j['entities'])==len(u['entities']);assert len(j['terms'])==len(u['terms']);assert all(type(v) is bool for v in j['atoms']+j['entities']+j['terms'])
  summary[scope]=dict(whole_correct=sum(u['score_whole'] and all(j['atoms']) and not j['errors'] for u,j in zip(us,chosen)),whole_total=sum(u['score_whole'] for u in us),atoms_correct=sum(sum(j['atoms']) for j in chosen),atoms_total=sum(len(u['atoms']) for u in us),entities_correct=sum(sum(j['entities']) for j in chosen),entities_total=sum(len(u['entities']) for u in us),terms_correct=sum(sum(j['terms']) for j in chosen),terms_total=sum(len(u['terms']) for u in us),errors={k:sum(k in j['errors'] for j in chosen) for k in ['format','identity','term','number','meaning','unsupported','relation','negation']},baseline=previous['cs2_auto_'+scope])
 times=sorted(r['inference_ms'] for r in rs)
 result=dict(scope='AI-assisted development evaluation, nonblind manual judgments; same frozen references; no phone/default-VAD claim',new_generation_calls=sum(v['generation_calls'] for v in screens.values())+len(rs),full_generation_calls=len(rs),screen=screens,summary=summary,mechanics=dict(subtitles=sum(r['status']=='subtitle' for r in rs),invalid=sum(r['status']=='invalid' for r in rs),no_speech=sum(r['status']=='no_speech' for r in rs),ready=sum(r['display']['standard']['status']=='ready' for r in rs),p50_ms=statistics.median(times),p95_ms=times[int(.95*len(times))],max_hints_characters=max(len(r['applied_hints']) for r in rs)),reference_sha256=sha(FULL/'reference.json'),display_sha256=sha(FULL/'display.jsonl'),adopt_default=False)
 (OUT/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 text=['# 最后版提示词：逐句参考、程序显示与判分','','判分者：当前会话模型，非独立人工盲审；沿用冻结参考及旧判分口径。','']
 oldjs=read(OLD/'judgments.json')['units']['cs2_auto']
 for u in refs:
  j=js[u['id']];text += [f"## {u['id']} · {u['start_ms']/1000:.3f}–{u['end_ms']/1000:.3f}s",'',u['reference_zh'],'',f"原基线：{sum(oldjs[u['id']]['atoms'])}/{len(u['atoms'])}事实；最后版：{sum(j['atoms'])}/{len(u['atoms'])}事实；错误：{', '.join(j['errors']) or '无'}",'',j['note'],'']
  text += [f"- {'✓' if ok else '✗'} {a}" for a,ok in zip(u['atoms'],j['atoms'])];text+=['']
  for r in rs:
   if r['source_id']==u['source_id'] and r['window'] in j['windows']:
    text += [f"**W{r['window']} · {r['status']}**",'',r['raw'],'','实际显示：'+(r['display']['standard']['chinese'] or '[无字幕]'),'']
 (OUT/'逐句对照.md').write_text('\n'.join(text));print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
