"""Aggregate an explicitly authored semantic judgment ledger; never an LLM scorer.
Use `review` to expose every frozen criterion beside actual controller output.
"""
import argparse,hashlib,json,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evaluation/results/cs-domain-20261020/product_round_v2'
REF=OUT/'reference.json'
def read(p):return json.loads(p.read_text())
def rows():return [json.loads(l) for l in (OUT/'display.jsonl').read_text().splitlines()]
def review():
 rs=rows();refs=read(REF)['units'];lines=[]
 for arm in ['no_corpus','cs2_auto']:
  for src in ['clip','clip_match_demo2','clip_match_demo3','clip_interview_niko']:
   lines.append('\n'+arm+' '+src)
   for r in rs:
    if r['arm']==arm and r['source_id']==src:lines.append(f"W{r['window']} {r['start_ms']/1000:.2f}-{r['end_ms']/1000:.2f} [{r['status']}] EN {r['english']}\nZH {r['display']['standard']['chinese']}"+(f"\nHINT {r['applied_hints']}" if arm=='cs2_auto' else ''))
 print('\n'.join(lines))
def audit():
 refs=read(REF)['units'];rs=rows();m=read(OUT/'manifest.json');judge=read(OUT/'judgments.json')
 assert len(rs)==m['request_budget'] and len({r['sequence'] for r in rs})==len(rs)
 assert judge['reference_sha256']==hashlib.sha256(REF.read_bytes()).hexdigest()
 assert judge['display_sha256']==hashlib.sha256((OUT/'display.jsonl').read_bytes()).hexdigest()
 judgments=judge['units'];summary={}
 for arm in m['arms']:
  for scope in ['primary_match','secondary_interview']:
   chosen=[u for u in refs if (u['source_id']=='clip_interview_niko')==(scope=='secondary_interview')]
   entries=[]
   for u in chosen:
    j=judgments[arm][u['id']]
    assert len(j['atoms'])==len(u['atoms'])
    assert all(type(v) is bool for v in j['atoms'])
    assert len(j['entities'])==len(u['entities'])
    assert len(j['terms'])==len(u['terms'])
    assert all(type(v) is bool for v in j['entities']+j['terms'])
    whole=u['score_whole'] and all(j['atoms']) and not j['errors']
    entries.append((u,j,whole))
   summary[arm+'_'+scope]=dict(whole_correct=sum(w for u,j,w in entries),whole_total=sum(u['score_whole'] for u,j,w in entries),atoms_correct=sum(sum(j['atoms']) for u,j,w in entries),atoms_total=sum(len(j['atoms']) for u,j,w in entries),entities_correct=sum(sum(j['entities']) for u,j,w in entries),entities_total=sum(len(j['entities']) for u,j,w in entries),terms_correct=sum(sum(j['terms']) for u,j,w in entries),terms_total=sum(len(j['terms']) for u,j,w in entries),error_units={k:sum(k in j['errors'] for u,j,w in entries) for k in ['identity','term','number','negation','unsupported','relation','meaning']})
 stats={}
 for arm in m['arms']:
  chosen=[r for r in rs if r['arm']==arm];t=sorted(r['inference_ms'] for r in chosen)
  stats[arm]=dict(windows=len(chosen),parsed_subtitles=sum(r['status']=='subtitle' for r in chosen),invalid=sum(r['status']=='invalid' for r in chosen),no_speech=sum(r['status']=='no_speech' for r in chosen),display_ready=sum(r['display']['standard']['status']=='ready' for r in chosen),verification_windows=sum(r['verification'] for r in chosen),hint_changed_from_domain=sum(r['applied_hints'] not in ['','CS2 broadcast.'] for r in chosen),inference_p50_ms=statistics.median(t),inference_p95_ms=t[min(len(t)-1,int(.95*len(t)))],inference_total_ms=sum(t),inferred_maps=sorted({r['inferred_map'] for r in chosen if r['inferred_map']}))
 styles={}
 for style in ['natural','community']:
  chosen=[r for r in rs if r['arm']=='cs2_auto'];changes=[dict(source_id=r['source_id'],window=r['window'],english=r['english'],standard=r['display']['standard']['chinese'],changed=r['display'][style]['chinese']) for r in chosen if r['display']['standard']['chinese']!=r['display'][style]['chinese']]
  styles[style]=dict(changed_windows=len(changes),nicknames=sum(r['styles'].get(style,{}).get('nicknames',0) for r in chosen),playful=sum(r['styles'].get(style,{}).get('playful',False) for r in chosen),localized_rules=sum(r['styles'].get(style,{}).get('localized',0) for r in chosen),changes=changes)
 # Correction comparison uses exactly the Chinese sent to Dart, after native style.
 corrections=[dict(arm=r['arm'],source_id=r['source_id'],window=r['window'],english=r['english'],before=r['styles']['standard']['chinese'],after=r['display']['standard']['chinese']) for r in rs if r['status']=='subtitle' and r['display']['standard']['status']=='ready' and r['styles']['standard']['chinese']!=r['display']['standard']['chinese']]
 per_source={}
 for arm in m['arms']:
  for src in [v['source_id'] for v in m['sources']]:
   us=[u for u in refs if u['source_id']==src];js=[judgments[arm][u['id']] for u in us]
   per_source[arm+'_'+src]=dict(whole_correct=sum(u['score_whole'] and all(j['atoms']) and not j['errors'] for u,j in zip(us,js)),whole_total=sum(u['score_whole'] for u in us),atoms_correct=sum(sum(j['atoms']) for j in js),atoms_total=sum(len(u['atoms']) for u in us))
 expected={'clip':'Dust2','clip_match_demo2':'Mirage','clip_match_demo3':'Nuke'}
 scene=[dict(source_id=r['source_id'],window=r['window'],inferred=r['inferred_map'],expected=expected[r['source_id']]) for r in rs if r['arm']=='cs2_auto' and r['source_id'] in expected and r['inferred_map']]
 scene_metrics=dict(known_map_windows=47,confirmed_windows=len(scene),correct_confirmed_windows=sum(v['inferred']==v['expected'] for v in scene),wrong_confirmed_windows=sum(v['inferred']!=v['expected'] for v in scene),rows=scene,unit='post-result window states; not independent map sessions or production accuracy')
 result=dict(scope='AI-assisted development evaluation, manually authored nonblind judgments; no independent human quality certification',summary=summary,per_source=per_source,scene=scene_metrics,mechanics=stats,styles=styles,corpus_corrections=corrections,requests_successful=len(rs),requests_failed_recorder=1,requests_total_including_failed=1+len(rs),reference_sha256=judge['reference_sha256'],display_sha256=judge['display_sha256'])
 (OUT/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 lines=['# CS 实音频逐句判分与实际字幕','',result['scope'],'','判分者：当前会话模型。每个布尔判定均由下方逐句证据和说明支持，脚本只汇总；不代表独立人工盲审。数字按分子/分母报告，部分正确不能算完整。','']
 for arm in m['arms']:
  lines+=['## '+arm,'']
  for u in refs:
   j=judgments[arm][u['id']]; selected=[r for r in rs if r['arm']==arm and r['source_id']==u['source_id'] and r['window'] in j['windows']]
   lines += [f"### {u['id']} · {u['start_ms']/1000:.3f}–{u['end_ms']/1000:.3f}s",'',u['reference_zh'],'',f"原子 {sum(j['atoms'])}/{len(u['atoms'])}；实体 {sum(j['entities'])}/{len(u['entities'])}；术语 {sum(j['terms'])}/{len(u['terms'])}；错误 {','.join(j['errors']) or '无'}",'',j['note'],'']
   lines += [f"- {'✓' if ok else '✗'} {a}" for a,ok in zip(u['atoms'],j['atoms'])]
   lines+=['']
   for r in selected:lines += [f"**W{r['window']} · {r['start_ms']/1000:.3f}–{r['end_ms']/1000:.3f}s**",'',r['english'],'',r['display']['standard']['chinese'] or f"[{r['status']}]",'']
 (OUT/'逐句对照与判分.md').write_text('\n'.join(lines))
 print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('action',choices=['review','audit']);a=p.parse_args();globals()[a.action]()
