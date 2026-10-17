"""Audit new requests and cached replay separately; no new model inference."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics

from score_reference import words,edit_distance

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evaluation/results/v020-convergence'


def main():
    m=json.loads((OUT/'gain2_manifest.json').read_text())
    data=(OUT/'gain2_requests.jsonl').read_bytes()
    rows=[json.loads(l) for l in data.decode().splitlines()]
    new=[r for r in rows if r['type']=='request']
    cached=[r for r in rows if r['type']=='cached_result']
    expected=[(c['id'],mode) for c in m['fresh'] for mode in c['mode_order']]
    if rows[-1]['type']!='complete' or len(new)!=46 or [(x['case_id'],x['mode']) for x in new]!=expected:
        raise RuntimeError('Incomplete/duplicate/reordered inference')
    if len(cached)!=82 or [{k:v for k,v in x.items() if k!='type'} for x in cached]!=m['cached']:
        raise RuntimeError('Cached replay/provenance mismatch')
    fresh={c['id']:c for c in m['fresh']}
    groups={}
    for group in ['synthetic_attenuated_whisper','quiet_music']:
        groups[group]={}
        for mode in ['baseline','gain2']:
            selected=[x for x in new if x['group']==group and x['mode']==mode]
            stats=dict(n=len(selected),statuses=dict(Counter(x['status'] for x in selected)),
                       median_decoder_ms=statistics.median(x['inference_ms'] for x in selected))
            if group=='quiet_music':
                stats['visible_fabrications']=sum(x['status']=='subtitle' for x in selected)
            else:
                total=sum(len(words(fresh[x['case_id']]['reference_en'])) for x in selected)
                errors=sum(edit_distance(words(fresh[x['case_id']]['reference_en']),words(x['english'])) for x in selected)
                stats.update(strict_correct=sum(words(x['english'])==words(fresh[x['case_id']]['reference_en']) for x in selected),
                             reference_words=total,literal_word_errors=errors,literal_wer=errors/total)
            groups[group][mode]=stats
    indexed={(x['case_id'],x['mode']):x for x in new}
    gains=[];losses=[];new_music=[];new_invalid=[]
    for c in m['fresh']:
        a,b=indexed[(c['id'],'baseline')],indexed[(c['id'],'gain2')]
        if c['group']=='synthetic_attenuated_whisper':
            ac=words(a['english'])==words(c['reference_en']);bc=words(b['english'])==words(c['reference_en'])
            if bc and not ac:gains.append(c['id'])
            if ac and not bc:losses.append(dict(case_id=c['id'],reference=c['reference_en'],baseline=a['raw'],candidate=b['raw']))
        elif b['status']=='subtitle' and a['status']!='subtitle':new_music.append(c['id'])
        if b['status']=='invalid' and a['status']!='invalid':
            new_invalid.append(dict(case_id=c['id'],baseline=a['raw'],candidate=b['raw'],reason=b['reason']))
    replay={}
    annotations=json.loads((OUT/'gain1_semantic_review.json').read_text())
    ratings={(x['case_id'],x['mode']):x for x in annotations}
    for group in ['fleurs_semantic','natural_whisper','ordinary','music','known_short_music']:
        replay[group]={}
        for mode in ['baseline','gain2']:
            selected=[x for x in cached if x['group']==group and x['mode']==mode]
            stats=dict(n=len(selected),new_model_requests=0,scope='Explicit historical cache/strategy replay, not independent confirmation or new timing')
            if group=='fleurs_semantic':
                en=zh=complete=0
                for x in selected:
                    rating=ratings[(x['case_id'],x['cache_mode'])]
                    en+=rating['english_units'].count('preserved');zh+=rating['chinese_units'].count('preserved')
                    complete+=all(v=='preserved' for v in rating['english_units']+rating['chinese_units'])
                stats.update(english_preserved=en,chinese_preserved=zh,semantic_units=18,strict_joint_cases=complete)
            elif group in ['natural_whisper','ordinary']:
                selected_rows=[x['actual_cached_result'] for x in selected]
                total=sum(len(words(x['original_reference']['reference_en'])) for x in selected)
                errors=sum(edit_distance(words(x['original_reference']['reference_en']),words(x['actual_cached_result']['english'])) for x in selected)
                stats.update(strict_source_matches=sum(words(x['original_reference']['reference_en'])==words(x['actual_cached_result']['english']) for x in selected),
                             reference_words=total,literal_word_errors=errors,literal_wer=errors/total)
            else:
                stats['visible_fabrications']=sum(x['actual_cached_result']['status']=='subtitle' for x in selected)
            replay[group][mode]=stats
    summary=dict(complete=True,new_requests=46,cached_logical_rows=82,new_groups=groups,replay_groups=replay,
        whisper_gains=gains,whisper_losses=losses,new_music_fabrication_cases=new_music,new_invalid_cases=new_invalid,
        continuation_gate_passed=False,decision='Reject candidate2: synthetic quiet-whisper strict9->8 and one new invalid; two gain candidates exhausted; third consecutive unsuccessful candidate overall.',
        independently_confirmed=False,verified_safe_optimization_gain=False,
        resources=rows[-1]['resources'],max_model_rss_kib=max(x['peak_rss_kib'] for x in new),
        result_sha256=hashlib.sha256(data).hexdigest(),manifest_sha256=hashlib.sha256((OUT/'gain2_manifest.json').read_bytes()).hexdigest(),
        caveat='Threshold is development-derived. Synthetic attenuated speech/music are not independent sources or natural weak speech. FLEURS semantic ratings are cached AI-assisted, not independent human ratings. No P95 or measured screen latency.')
    with (OUT/'gain2_summary.json').open('x') as f:f.write(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
