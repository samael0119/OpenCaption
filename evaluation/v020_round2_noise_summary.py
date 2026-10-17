"""Audit82 frozen paired requests and compute literal-reference diagnostics.

Semantic ratings are a separate AI-assisted review; don't replace them with WER.
Old fixtures are development cases, not independent source confidence evidence.
"""
from collections import Counter
import json
import math
import statistics

from score_reference import words, edit_distance
from v020_round2_noise import OUT, MANIFEST, OUTPUT, ROOT, verify, pilot


def wilson(success, n):
    if not n:
        return None
    z=1.959963984540054; p=success/n; d=1+z*z/n
    center=(p+z*z/(2*n))/d
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return [center-half,center+half]


def summarize():
    target=OUT/'summary.json'
    if target.exists():
        raise RuntimeError('Summary already saved; inspect instead')
    m=verify();rows=[json.loads(l) for l in OUTPUT.read_text().splitlines()]
    requests=[r for r in rows if r['type']=='request']
    expected=[(o['case_id'],mode) for o in m['order'] for mode in o['modes']]
    if rows[0]['type']!='metadata' or rows[-1]['type']!='complete' or len(requests)!=82:
        raise RuntimeError('Incomplete run')
    if [(r['case_id'],r['mode']) for r in requests]!=expected or [r['index'] for r in requests]!=list(range(82)):
        raise RuntimeError('Wrong order/index')
    if rows[0]['manifest_sha256']!=pilot.digest(MANIFEST) or rows[-1]['requests']!=82:
        raise RuntimeError('Wrong freeze/count')
    for r in [rows[0],rows[-1]]:
        limits=r['resources']
        if int(limits['memory.max'])>6*1024**3 or limits['memory.swap.max']!='0' or limits['memory.swap.current']!='0':
            raise RuntimeError('Memory/swap guard')
        events=dict(line.split() for line in limits['memory.events'].splitlines())
        if int(events.get('oom',0)) or int(events.get('oom_kill',0)):
            raise RuntimeError('OOM guard')
    cases={c['id']:c for c in m['cases']}
    paired={}
    for r in requests:
        c=cases[r['case_id']]
        if r['input_sha256']!=c['sha256' if r['mode']=='baseline' else 'noise_sha256']:
            raise RuntimeError('PCM selection mismatch')
        paired.setdefault(c['id'],{})[r['mode']]=r
    detail=[]
    for case_id,pair in paired.items():
        c=cases[case_id];reference=words(c.get('reference_en',''))
        entry=dict(case_id=case_id,group=c['group'],reference_en=c.get('reference_en',''),
                   reference_words=len(reference),baseline={},noise={})
        for mode,r in pair.items():
            entry[mode]=dict(status=r['status'],english=r['english'],chinese=r['chinese'],
                strict_match=r['status']=='subtitle' and words(r['english'])==reference,
                word_errors=edit_distance(reference,words(r['english'])),decoder_ms=r['inference_ms'],
                cold=r['index']==0,raw=r['raw'])
        entry['strict_gain']=not entry['baseline']['strict_match'] and entry['noise']['strict_match']
        entry['strict_loss']=entry['baseline']['strict_match'] and not entry['noise']['strict_match']
        detail.append(entry)
    groups={}
    for group in sorted({c['group'] for c in m['cases']}):
        subset=[d for d in detail if d['group']==group]
        result=dict(cases=len(subset),reference_words=sum(d['reference_words'] for d in subset),
            strict_gains=[d['case_id'] for d in subset if d['strict_gain']],
            strict_losses=[d['case_id'] for d in subset if d['strict_loss']])
        for mode in ['baseline','noise']:
            s=[d[mode] for d in subset];success=sum(r['strict_match'] for r in s)
            result[mode]=dict(statuses=dict(Counter(r['status'] for r in s)),strict_matches=success,
                strict_interval_case_iid_only=wilson(success,len(s)),
                word_errors=sum(r['word_errors'] for r in s),
                wer=sum(r['word_errors'] for r in s)/result['reference_words'] if result['reference_words'] else None,
                decoder_median_all_ms=statistics.median(r['decoder_ms'] for r in s),
                decoder_median_non_cold_ms=statistics.median(r['decoder_ms'] for r in s if not r['cold']))
        groups[group]=result
    summary=dict(complete=True,actual_requests=82,cache_reuse=0,files_verified=len(m['files']),groups=groups,
        paired_details=detail,semantic_review_pending=True,independent_acceptance=False,
        interval_note='Wilson intervals describe individual-fixture binomial uncertainty only; shared sources/speakers violate independence. Source-level paired CI cannot be reliably estimated from one whisper speaker/one music recording/one ordinary speaker. No confident population-gain claim.',
        latency_note='Decoder timing only, cold first request identified; CLI transform separate. No real display or formal end-to-endP95 measured.',
        peak_rss_kib=max(r['peak_rss_kib'] for r in requests),
        filter_cli_ms=dict(median=statistics.median(c['filter_cli_ms'] for c in m['cases']),
            maximum=max(c['filter_cli_ms'] for c in m['cases']),process_spawn_included=True),
        filter_delay_ms=25,scope=m['scope'],resources=rows[-1]['resources'])
    pilot.write_new(target,summary)
    print(json.dumps({k:v for k,v in summary.items() if k!='paired_details'},ensure_ascii=False,indent=2))


if __name__=='__main__':
    summarize()
