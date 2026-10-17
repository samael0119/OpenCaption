"""Audit frozen82 requests, literal metrics and exact-raw semantic cache reuse."""
from collections import Counter
import json
import statistics

from score_reference import words,edit_distance
from v020_semantic_rating_cache import frozen_judgment,preserved_count
from v020_round3_candidate import ROOT,OUT,MANIFEST,OUTPUT,verify,pilot


def main():
    target=OUT/'summary.json'
    if target.exists(): raise RuntimeError('Summary exists; inspect checkpoint')
    m=verify();rows=[json.loads(l) for l in OUTPUT.read_text().splitlines()]
    requests=[r for r in rows if r['type']=='request']
    starts=[r for r in rows if r['type']=='request_started']
    expected=[(c,b['mode'],i) for i,b in enumerate(m['blocks']) for c in b['case_ids']]
    if rows[-1]['type']!='complete' or len(requests)!=82 or len(starts)!=82:
        raise RuntimeError('Incomplete run; no quality conclusion')
    if [(r['case_id'],r['mode'],r['block']) for r in requests]!=expected:
        raise RuntimeError('Request order mismatch')
    if [r['index'] for r in requests]!=list(range(82)) or [r['index'] for r in starts]!=list(range(82)):
        raise RuntimeError('Duplicate/missing request index')
    if rows[0]['manifest_sha256']!=pilot.digest(MANIFEST): raise RuntimeError('Manifest mismatch')
    lifecycle=[(r['type'],r['block']) for r in rows if r['type'] in ['engine_initializing','engine_initialized','engine_closed']]
    wanted=[(t,i) for i in range(3) for t in ['engine_initializing','engine_initialized','engine_closed']]
    if lifecycle!=wanted: raise RuntimeError('Model lifetime integrity failed')
    for row in [rows[0],rows[-1]]:
        limits=row['resources'];events=dict(s.split() for s in limits['memory.events'].splitlines())
        if int(limits['memory.max'])>6*1024**3 or limits['memory.swap.current']!='0' or limits['memory.swap.max']!='0' or int(events['oom']) or int(events['oom_kill']):
            raise RuntimeError('Resource guard')
    refs={c['id']:c for c in m['cases']};records=pilot.read(OUT/'frozen_ratings.json')
    paired={};details=[];semantics=[]
    for r in requests:
        if r['input_sha256']!=refs[r['case_id']]['sha256']: raise RuntimeError('Source PCM changed')
        paired.setdefault(r['case_id'],{})[r['mode']]=r
    for case_id,pair in paired.items():
        case=refs[case_id];ref=words(case.get('reference_en',''))
        d=dict(case_id=case_id,group=case['group'],reference_en=case.get('reference_en',''),reference_words=len(ref))
        for mode,row in pair.items():
            d[mode]=dict(status=row['status'],english=row['english'],chinese=row['chinese'],raw=row['raw'],
                strict_match=row['status']=='subtitle' and words(row['english'])==ref,
                word_errors=edit_distance(ref,words(row['english'])),
                decoder_ms=row['inference_ms'],cold_after_load=row['cold_after_load'])
            if case['group']=='fleurs_semantic':
                judgment=frozen_judgment(case_id,row['raw'],case['semantic_units'],records)
                semantics.append(dict(case_id=case_id,mode=mode,raw=row['raw'],
                    semantic_units=case['semantic_units'],frozen_judgment=judgment,
                    independent_human_rating=False))
        d['strict_gain']=not d['auto']['strict_match'] and d['disabled']['strict_match']
        d['strict_loss']=d['auto']['strict_match'] and not d['disabled']['strict_match']
        details.append(d)
    groups={}
    for group in sorted({c['group'] for c in m['cases']}):
        selected=[d for d in details if d['group']==group]
        g=dict(cases=len(selected),reference_words=sum(d['reference_words'] for d in selected),
            strict_gains=[d['case_id'] for d in selected if d['strict_gain']],
            strict_losses=[d['case_id'] for d in selected if d['strict_loss']],
            raw_equal_pairs=sum(d['auto']['raw']==d['disabled']['raw'] for d in selected))
        for mode in ['auto','disabled']:
            values=[d[mode] for d in selected];warm=[r['decoder_ms'] for r in values if not r['cold_after_load']]
            errors=sum(r['word_errors'] for r in values)
            g[mode]=dict(statuses=dict(Counter(r['status'] for r in values)),
                strict_matches=sum(r['strict_match'] for r in values),word_errors=errors,
                wer=errors/g['reference_words'] if g['reference_words'] else None,
                decoder_median_all_ms=statistics.median(r['decoder_ms'] for r in values),
                decoder_median_non_cold_ms=statistics.median(warm) if warm else None)
        groups[group]=g
    totals={};pending=[]
    for mode in ['auto','disabled']:
        rated=[r for r in semantics if r['mode']==mode and r['frozen_judgment'] is not None]
        missing=[r['case_id'] for r in semantics if r['mode']==mode and r['frozen_judgment'] is None]
        pending.extend(dict(mode=mode,case_id=c) for c in missing)
        totals[mode]=dict(cached_outputs=len(rated),unrated_case_ids=missing,denominator_units=18,
            en_preserved_cached=sum(preserved_count(r['frozen_judgment']['en']) for r in rated),
            zh_preserved_cached=sum(preserved_count(r['frozen_judgment']['zh']) for r in rated),
            note='Partial counts are not the full semantic score while any outputs are unrated')
    summary=dict(complete=True,actual_requests=82,engine_loads=3,groups=groups,paired_details=details,
        semantic_cache=totals,semantic_review_pending=pending,semantic_outputs=semantics,
        raw_equal_pairs=sum(d['auto']['raw']==d['disabled']['raw'] for d in details),
        engine_initializations=[{k:r[k] for k in ['block','mode','initialization_ms','actual_requested_fields']} for r in rows if r['type']=='engine_initialized'],
        resources=rows[-1]['resources'],independent_acceptance=False,
        interval_note='Observed reused development data with one whisper speaker/ordinary speaker/music source; source-level CI cannot be reliably estimated. No population gain claim.',
        timing_note='Decoder costs,3 cold-after-load calls separately marked; initialization separate. No physical paint or formal end-to-endP95.',
        comparison='Requested model-default auto vs explicitFalse; no asserted observed internal MTP=True state')
    pilot.write_new(target,summary)
    print(json.dumps({k:v for k,v in summary.items() if k not in ['paired_details','semantic_outputs']},ensure_ascii=False,indent=2))


if __name__=='__main__': main()
