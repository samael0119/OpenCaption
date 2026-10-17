"""Frozen local-only tests: sentinel adapter and same-template terminology.

No product parser is changed. Gold gaps and attenuated speech are diagnostic
controls, not independently labelled background-music/whisper recordings.
"""
from __future__ import annotations

import argparse
from array import array
from dataclasses import asdict
import hashlib
import json
import re
import statistics
import time

from e2e_protocol import ParsedOutput, parse_output
from s0_context_roster import IdentityIndex
from s0_scene_state import MapEvidence
from s0_probe import OUT as S0, INPUT, SceneIndex, pcm_file, write_json, percentile
from s0_protocol_live import ProbeRuntime
from score_reference import words, edit_distance
from score_srt import read_srt
from terminology import Terminology

OUT = S0 / 'local_followup'
# Entire message, exactly two nonempty fields, never extract a sentinel from
# inside a sentence or a reply with explanations. Missing language stays invalid.
_BALANCED_NONE = re.compile(
    r'\A(?:English\s*[:：]\s*)?\[NONE\][ \t]*\r?\n[ \t]*'
    r'(?:(?:and|和)\s*)?(?:Chinese|中文)\s*[:：]\s*\[NONE\]\Z', re.I)


def candidate_parse(raw):
    original = parse_output(raw)
    if original.status == 'invalid' and _BALANCED_NONE.fullmatch(raw.strip()):
        return ParsedOutput('no_speech', reason='balanced_exact_sentinel')
    return original


def scale_pcm(pcm, db):
    value = array('h'); value.frombytes(pcm)
    factor = 10 ** (db / 20)
    return array('h', (round(v * factor) for v in value)).tobytes()


def exact_zero_pcm(pcm):
    if not pcm or len(pcm)%2:
        raise ValueError('Expected nonempty PCM16 samples')
    return not any(pcm)


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    cues = {c['id']: c for c in read_srt(INPUT/'clip_gold_bilingual.srt')}
    targets = {
        1: (['donk'], [('headshot', ['爆头'])]),
        3: (['tN1R', 'sh1ro'], []),
        4: (['xertioN'], []),
        6: (['sh1ro'], [('Scout', ['鸟狙'])]),
        9: (['xertioN'], [('Scout', ['鸟狙']), ('M4', ['M4'])]),
        12: (['xertioN'], []),
        17: (['Spirit'], []),
        23: (['zont1x'], []),
        28: (['sh1ro', 'donk'], [('Berettas', ['双枪'])]),
        29: (['MOUZ'], []),
    }
    speech = [dict(**cues[i], entities=entities, terms=terms, kind='gold_speech',
                   source='clip', gain_db=0)
              for i, (entities, terms) in targets.items()]
    assert all(c['end_ms']-c['start_ms']<=5000 for c in speech)
    controls = [dict(id='zero_1000',source='zero',start_ms=0,end_ms=1000,kind='zero',gain_db=0),
                dict(id='zero_5000',source='zero',start_ms=0,end_ms=5000,kind='zero',gain_db=0),
                dict(id='gap_start',source='clip',start_ms=100,end_ms=450,kind='gold_gap',gain_db=0),
                dict(id='gap_37',source='clip',start_ms=37652,end_ms=38479,kind='gold_gap',gain_db=0),
                dict(id='gap_71',source='clip',start_ms=71546,end_ms=72581,kind='gold_gap',gain_db=0),
                dict(**{**speech[0], 'id':'attenuated_18', 'kind':'attenuated_speech','gain_db':-18}),
                dict(**{**speech[0], 'id':'attenuated_30', 'kind':'attenuated_speech','gain_db':-30})]
    hints = ('Scene: Spirit vs MOUZ on Dust II. Name spellings: donk, sh1ro, tN1R, '
             'xertioN, zont1x. Scout=鸟狙; M4=M4; Berettas=双枪; headshot=爆头.')
    manifest = dict(schema=1, template='conditional_compact', context=768, output=128,
        model_sha256='181938105e0eefd105961417e8da75903eacda102c4fce9ce90f50b97139a63c',
        gold_sha256=hashlib.sha256((INPUT/'clip_gold_bilingual.srt').read_bytes()).hexdigest(),
        speech=speech, controls=controls, hints=hints, repeats=2,
        scope='Known scene/terms are oracle data; same used match, not independent validation',
        quality='Entity spelling and Chinese term occurrence only; no whole-sentence semantic score')
    write_json(OUT/'manifest.json', manifest)
    print('Frozen',len(speech),'gold cues;',len(controls),'controls;',40+len(controls)*2,'requests')


def inferred():
    manifest_bytes = (OUT/'manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    assert hashlib.sha256((INPUT/'clip_gold_bilingual.srt').read_bytes()).hexdigest()==manifest['gold_sha256']
    jobs = [(1,c,style) for c in manifest['controls'] for style in ['no_hint','oracle_hint']]
    jobs += [(repeat,c,style) for repeat in [1,2] for c in manifest['speech']
             for style in (['no_hint','oracle_hint'] if repeat==1 else ['oracle_hint','no_hint'])]
    runtime = ProbeRuntime()
    identity, terms = IdentityIndex(), Terminology()
    try:
        with (OUT/'inference.jsonl').open('w') as report:
            report.write(json.dumps(dict(type='metadata', manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
                jobs=len(jobs), warmup=1, init_ms=runtime.init_ms, backend='CPU',threads=4,mtp=True,
                context=768,output=128,scope=manifest['scope']))+'\n')
            for number,(repeat,case,style) in enumerate(jobs,1):
                pcm = (bytes((case['end_ms']-case['start_ms'])*32) if case['source']=='zero' else
                    pcm_file(S0/(case['source']+'.wav'))[case['start_ms']*32:case['end_ms']*32])
                if case['gain_db']:
                    pcm = scale_pcm(pcm,case['gain_db'])
                hint = manifest['hints'] if style=='oracle_hint' else ''
                result = runtime.call(pcm,'conditional_compact',hint)
                candidate = candidate_parse(result.get('raw',''))
                corrected = dict(english=identity.normalize(candidate.english or ''),
                    chinese=terms.correct(candidate.english or '',candidate.chinese or '')) if candidate.status=='subtitle' else None
                row = dict(type='window',case_id=case['id'],kind=case['kind'],
                    repeat=repeat,condition=style,start_ms=case['start_ms'],end_ms=case['end_ms'],
                    **result,candidate=asdict(candidate),corrected=corrected)
                report.write(json.dumps(row,ensure_ascii=False)+'\n');report.flush()
                print(number,len(jobs),case['id'],style,result['status'],'->',candidate.status,result['inference_ms'],flush=True)
            report.write(json.dumps(dict(type='complete',completed=len(jobs)))+'\n')
    finally:
        runtime.close()


def quality(rows,cases,corrected=False):
    entity_hits=chinese_entity_hits=entity_total=term_hits=term_total=valid=0
    reference=[];hypothesis=[]
    details=[]
    for row in rows:
        case=cases[row['case_id']]
        parsed=row['candidate']
        text = row['corrected'] if corrected else parsed
        en = (text.get('english') or '') if text else ''
        zh = (text.get('chinese') or '') if text else ''
        valid += parsed['status']=='subtitle'
        reference+=words(case['english']);hypothesis+=words(en)
        hits = {e:bool(re.search(r'(?<![A-Za-z0-9])'+re.escape(e)+r'(?![A-Za-z0-9])',en,re.I)) for e in case['entities']}
        zh_hits = {e:bool(re.search(r'(?<![A-Za-z0-9])'+re.escape(e)+r'(?![A-Za-z0-9])',zh,re.I)) for e in case['entities']}
        matches = {e:any(v in zh for v in targets) for e,targets in case['terms']}
        entity_hits+=sum(hits.values());entity_total+=len(hits)
        chinese_entity_hits+=sum(zh_hits.values())
        term_hits+=sum(matches.values());term_total+=len(matches)
        details.append(dict(case_id=row['case_id'],repeat=row['repeat'],entities=hits,chinese_entities=zh_hits,terms=matches,english=en,chinese=zh))
    return dict(n=len(rows),subtitle=valid,entity_hits=entity_hits,entity_total=entity_total,
        chinese_entity_hits=chinese_entity_hits,term_occurrences=term_hits,term_total=term_total,english_wer=edit_distance(reference,hypothesis)/len(reference),
        median_ms=statistics.median(r['inference_ms'] for r in rows),details=details)


def summarize():
    manifest=json.loads((OUT/'manifest.json').read_text())
    rows=[json.loads(s) for s in (OUT/'inference.jsonl').read_text().splitlines()]
    assert rows[-1]['type']=='complete'
    assert rows[0]['manifest_sha256']==hashlib.sha256((OUT/'manifest.json').read_bytes()).hexdigest()
    cases={c['id']:c for c in manifest['speech']}
    summary=dict(metadata=rows[0],speech={},controls={})
    for style in ['no_hint','oracle_hint']:
        speech=[r for r in rows if r.get('condition')==style and r['kind']=='gold_speech']
        summary['speech'][style]=quality(speech,cases)
        summary['speech'][style+'_corrected']=quality(speech,cases,True)
        for kind in ['zero','gold_gap','attenuated_speech']:
            selected=[r for r in rows if r.get('condition')==style and r['kind']==kind]
            summary['controls'][style+'_'+kind]=dict(n=len(selected),
                original={s:sum(r['status']==s for r in selected) for s in ['no_speech','subtitle','invalid','exception']},
                candidate={s:sum(r['candidate']['status']==s for r in selected) for s in ['no_speech','subtitle','invalid']},
                outputs=[dict(id=r['case_id'],raw=r.get('raw'),status=r['candidate']['status']) for r in selected])
    write_json(OUT/'summary.json',summary)
    print(json.dumps({k:{a:{b:c for b,c in v.items() if b not in ['details','outputs']} for a,v in x.items()}
        for k,x in summary.items() if k!='metadata'},ensure_ascii=False,indent=2))


def routing():
    """Explicit offline routing check; reuses raw predictions, no new inference.

    Shows what an exact-zero prefilter would route. No counterfactual timing
    claim, and no suppression of nonzero low-level/background samples.
    """
    manifest=json.loads((OUT/'manifest.json').read_text())
    cases={c['id']:c for c in manifest['controls']}
    rows=[json.loads(s) for s in (OUT/'inference.jsonl').read_text().splitlines()]
    assert rows[-1]['type']=='complete'
    output=[]
    for row in rows:
        if row.get('kind') not in ['zero','gold_gap','attenuated_speech']:
            continue
        case=cases[row['case_id']]
        pcm=(bytes((case['end_ms']-case['start_ms'])*32) if case['source']=='zero' else
             pcm_file(S0/'clip.wav')[case['start_ms']*32:case['end_ms']*32])
        if case['gain_db']:
            pcm=scale_pcm(pcm,case['gain_db'])
        bypass=exact_zero_pcm(pcm)
        output.append(dict(id=row['case_id'],condition=row['condition'],kind=row['kind'],
            bypass_model=bypass,status='no_speech' if bypass else row['candidate']['status']))
    assert len(output)==14 and sum(r['bypass_model'] for r in output)==4
    assert not any(r['bypass_model'] for r in output if r['kind']!='zero')
    write_json(OUT/'routing.json',dict(mode='offline prefilter check using cached predictions; no new timing',rows=output))
    print('14 routing checks: 4 exact-zero requests bypass; all 10 nonzero inputs retained')


def relevant_callouts(index,map_name,recent,limit=4):
    """Exact mention + map relation retrieval, no extra LLM or embeddings."""
    ranked=[]
    seen=set()
    for term in index.maps.get(map_name,[]):
        if term['id'] in seen or term.get('category')!='map_callout':continue
        seen.add(term['id'])
        matches=[]
        for i,text in enumerate(recent):
            for alias in [term['english'],*term.get('aliases',[])]:
                pattern=r'\b(?:through|towards|into|at|in|up|down|on|from|holding|taking|take)\s+(?:the\s+)?'+re.escape(alias)+r'\b'
                if any(not MapEvidence.negated(text,m.start()) for m in re.finditer(pattern,text,re.I)):
                    matches.append(i)
        if matches:ranked.append((max(matches),term))
    return [t for _,t in sorted(ranked,key=lambda r:(-r[0],r[1]['id']))[:limit]]


def scene_prepare():
    path=S0/'supplement.jsonl'
    rows=[json.loads(s) for s in path.read_text().splitlines()]
    assert rows[-1]['type']=='complete'
    baseline=[r for r in rows if r.get('group')=='historical_match' and r.get('status')=='subtitle']
    index=SceneIndex();cases=[]
    for start,end in [(35000,40000),(40000,45000),(45000,48006)]:
        # Request is submitted at chunk end. Prior ASR must both use preceding
        # audio and have completed by that submission time on the cached trace.
        past=[r for r in baseline if r['end_ms']<=start and r['end_ms']+r['inference_ms']<=end]
        state=MapEvidence()
        for row in past:state.update(row['english'],row['end_ms'],row['start_ms'])
        view=state.view(end)
        terms=relevant_callouts(index,view['map'],[r['english'] for r in past[-3:]])
        hint=('Scene map: '+view['map']+'. Relevant callouts: '+
              '; '.join(t['english']+'='+t['chinese'] for t in terms)) if view['map'] else ''
        cases.append(dict(start_ms=start,end_ms=end,state=view,auto_hint=hint,
            oracle_hint='Scene map: Nuke. Relevant callouts: Heaven=天堂; Hell=地狱; Vent=通风管道.',
            past_ends=[r['end_ms'] for r in past],retrieved_ids=[t['id'] for t in terms]))
    write_json(OUT/'scene_manifest.json',dict(cases=cases,baseline_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        scope='Cached prior no-hint ASR, not closed-loop generated context; 3 known used-match windows, no independent gold',
        timing='Prior end+measured service <= next submission, ignores OS overhead and display'))
    print(json.dumps(cases,ensure_ascii=False,indent=2))


def scene_infer():
    raw=(OUT/'scene_manifest.json').read_bytes();manifest=json.loads(raw)
    assert hashlib.sha256((S0/'supplement.jsonl').read_bytes()).hexdigest()==manifest['baseline_sha256']
    runtime=ProbeRuntime()
    try:
        with (OUT/'scene_inference.jsonl').open('w') as report:
            report.write(json.dumps(dict(type='metadata',manifest_sha256=hashlib.sha256(raw).hexdigest(),
                warmup=1,jobs=9,context=768,output=128,scope=manifest['scope']))+'\n')
            for case in manifest['cases']:
                pcm=pcm_file(S0/'clip_match_demo3.wav')[case['start_ms']*32:case['end_ms']*32]
                for style in ['no_hint','oracle_hint','auto_hint']:
                    result=runtime.call(pcm,'conditional_compact',case.get(style,'') if style!='no_hint' else '')
                    row=dict(type='window',condition=style,start_ms=case['start_ms'],end_ms=case['end_ms'],
                        **result,candidate=asdict(candidate_parse(result.get('raw',''))))
                    report.write(json.dumps(row,ensure_ascii=False)+'\n');report.flush()
                    print(case['start_ms'],style,result['status'],result['inference_ms'],flush=True)
            report.write(json.dumps(dict(type='complete',completed=9))+'\n')
    finally:runtime.close()


def scene_summarize():
    rows=[json.loads(s) for s in (OUT/'scene_inference.jsonl').read_text().splitlines()]
    assert rows[-1]['type']=='complete'
    assert rows[0]['manifest_sha256']==hashlib.sha256((OUT/'scene_manifest.json').read_bytes()).hexdigest()
    summary={}
    for style in ['no_hint','oracle_hint','auto_hint']:
        selected=[r for r in rows if r.get('condition')==style]
        summary[style]=dict(n=len(selected),subtitle=sum(r['candidate']['status']=='subtitle' for r in selected),
            median_ms=statistics.median(r['inference_ms'] for r in selected),
            max_text_tokens=max(r['text_tokens'] for r in selected),
            max_conversation_tokens=max(r.get('conversation_tokens',0) for r in selected),
            outputs=[dict(start_ms=r['start_ms'],english=r['candidate']['english'],chinese=r['candidate']['chinese']) for r in selected])
    write_json(OUT/'scene_summary.json',dict(scope=rows[0]['scope'],groups=summary))
    print(json.dumps(summary,ensure_ascii=False,indent=2))


def scene_bench():
    rows=[json.loads(s) for s in (S0/'supplement.jsonl').read_text().splitlines()]
    rows=[r for r in rows if r.get('group')=='historical_match' and r.get('status')=='subtitle']
    index=SceneIndex();costs=[];initial=[]
    for repeat in range(10):
        began=time.perf_counter();state=MapEvidence();initial.append((time.perf_counter()-began)*1000)
        recent=[]
        for row in rows:
            began=time.perf_counter()
            view=state.update(row['english'],row['end_ms'],row['start_ms']);recent.append(row['english'])
            relevant_callouts(index,view['map'],recent[-3:])
            costs.append((time.perf_counter()-began)*1000)
    result=dict(scope='Standalone rule update+map-filtered location retrieval, first regex compilation included; no model resident',
        n=len(costs),p50_ms=statistics.median(costs),p95_ms=percentile(costs,.95),max_ms=max(costs),
        state_init_p50_ms=statistics.median(initial))
    write_json(OUT/'scene_cost.json',result)
    print(json.dumps(result))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=['prepare','infer','summarize','routing','scene_prepare','scene_infer','scene_summarize','scene_bench'])
    args=parser.parse_args()
    {'prepare':prepare,'infer':inferred,'summarize':summarize,'routing':routing,
     'scene_prepare':scene_prepare,'scene_infer':scene_infer,'scene_summarize':scene_summarize,'scene_bench':scene_bench}[args.phase]()
