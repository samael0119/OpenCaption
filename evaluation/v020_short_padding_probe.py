"""One frozen leading-zero-padding candidate on unseen keyword speakers.

No capture delay, normalization, prompt/label tuning or product change. Padding
is tested once, against the original input, on 48 new public keyword clips.
"""
from array import array
from collections import Counter
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re
import statistics
import sys
import tarfile
import wave

from v020_prepare_short_answers import ROOT, OUT, ARCHIVE, LABELS


def prepare():
    path = OUT/'short_padding_manifest.json'
    if path.exists():
        raise RuntimeError('Already frozen: never reselect based on model output')
    prior = json.loads((OUT/'short_answer_cases.json').read_text())
    excluded = {c['speaker_id'] for c in prior['cases']}
    speakers = set(excluded)
    assets = OUT/'short_padding'
    assets.mkdir(exist_ok=False)
    cases = []
    with tarfile.open(ARCHIVE, 'r:gz') as archive:
        members = sorted((m for m in archive if m.isfile()), key=lambda m:m.name)
        for label,chinese in LABELS.items():
            selected = 0
            for member in members:
                name = Path(member.name).name
                match = re.fullmatch(r'(?:(\w+)_)?([0-9a-f]{8})_nohash_(\d+)\.wav(?:\.wav)?', name)
                if not match:
                    continue
                source_label = match.group(1) or Path(member.name).parent.name
                speaker = match.group(2)
                if source_label != label or speaker in speakers:
                    continue
                content = archive.extractfile(member).read()
                with wave.open(io.BytesIO(content)) as wav:
                    assert (wav.getnchannels(),wav.getsampwidth(),wav.getframerate()) == (1,2,16000)
                    samples = wav.getnframes(); pcm = wav.readframes(samples)
                assert 0 < samples <= 17600
                speakers.add(speaker)
                case_id = f'{label}-{speaker}-{match.group(3)}'
                original = assets/(case_id+'.wav'); original.write_bytes(content)
                padded = assets/(case_id+'-leading2s.wav')
                padded_pcm = bytes((32000-samples)*2)+pcm
                with wave.open(str(padded),'wb') as wav:
                    wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000);wav.writeframes(padded_pcm)
                # Preserve every original sample in order, without adding
                # nonzero samples, trimming, gain or model-generated reference.
                with wave.open(str(padded)) as wav:
                    actual = wav.readframes(wav.getnframes())
                assert len(actual)==64000 and actual[-len(pcm):]==pcm and not any(actual[:-len(pcm)])
                cases.append(dict(id=case_id,kind='public_single_keyword',label=label,
                    reference_en=label,reference_zh_options=chinese,speaker_id=speaker,
                    source_member=member.name,samples=samples,duration_seconds=samples/16000,
                    path=str(original.relative_to(ROOT)),sha256=hashlib.sha256(content).hexdigest(),
                    padded_path=str(padded.relative_to(ROOT)),padded_sha256=hashlib.sha256(padded.read_bytes()).hexdigest()))
                selected += 1
                if selected==4:
                    break
            assert selected==4
    classes = json.loads((OUT/'controller_closed_loop_manifest.json').read_text())['classes']
    path.write_text(json.dumps(dict(frozen_utc=datetime.now(timezone.utc).isoformat(),
        cases=cases,classes=classes,prior_speakers_excluded=sorted(excluded),new_speakers=48,
        source_url=prior['source_url'],attribution=prior['attribution'],license=prior['license'],
        source_md5=prior['source_md5'],reference_scope=prior['reference_scope'],
        selection='First four filename-sorted globally unseen speakers per zero..nine/yes/no; no output-based selection.',
        candidate='Leading exact zeros to total 2s model input; original timestamps/capture unchanged; no product enablement.',
        acceptance=dict(min_joint_gain=2,no_new_no_speech=True,no_new_invalid=True,
            no_source_regression_for_no_or_six=True,max_median_service_ratio=1.5,max_p95_service_ms=3000),
        scope='New keyword speakers; one audio-shape candidate, not CS2/Chinese sentence, real whisper/music or whole product acceptance.'),ensure_ascii=False,indent=2)+'\n')


def summarize(manifest,rows):
    from v020_short_answer_validation import score
    by_id={c['id']:c for c in manifest['cases']}
    groups={}
    pairs={}
    for mode in ['original','leading2s']:
        selected=[r for r in rows if r['input_mode']==mode]
        scores=[score(r,by_id[r['case_id']]) for r in selected]
        times=sorted(r['inference_ms'] for r in selected)
        groups[mode]=dict(n=len(selected),statuses=dict(Counter(r['status'] for r in selected)),
            source_correct=sum(s['source_keyword_ok'] for s in scores),joint_correct=sum(s['joint_keyword_ok'] for s in scores),
            median_ms=statistics.median(times),p95_ms=times[math.ceil(.95*len(times))-1])
        pairs[mode]={r['case_id']:(r,s) for r,s in zip(selected,scores)}
    transitions=[]
    for case in manifest['cases']:
        a,sa=pairs['original'][case['id']];b,sb=pairs['leading2s'][case['id']]
        transitions.append(dict(id=case['id'],label=case['label'],original=a['status'],candidate=b['status'],
            original_source=sa['source_keyword_ok'],candidate_source=sb['source_keyword_ok'],
            original_joint=sa['joint_keyword_ok'],candidate_joint=sb['joint_keyword_ok']))
    limits=manifest['acceptance'];a=groups['original'];b=groups['leading2s']
    checks=dict(joint_gain=b['joint_correct']-a['joint_correct']>=limits['min_joint_gain'],
        no_new_no_speech=not any(t['original']!='no_speech' and t['candidate']=='no_speech' for t in transitions),
        no_new_invalid=not any(t['original']!='invalid' and t['candidate']=='invalid' for t in transitions),
        critical_no_six=not any(t['label'] in ['no','six'] and t['original_source'] and not t['candidate_source'] for t in transitions),
        service_ratio=b['median_ms']/a['median_ms']<=limits['max_median_service_ratio'],
        p95=b['p95_ms']<=limits['max_p95_service_ms'])
    (OUT/'short_padding_summary.json').write_text(json.dumps(dict(complete=True,requests=len(rows),groups=groups,
        transitions=transitions,checks=checks,candidate_passed=all(checks.values()),
        product_enabled=False,scope=manifest['scope']),ensure_ascii=False,indent=2)+'\n')


def run():
    from v020_runtime_validation import Protocol,runtime,infer,append
    manifest_path=OUT/'short_padding_manifest.json';manifest=json.loads(manifest_path.read_text())
    output=OUT/'short_padding.jsonl'
    if output.exists():
        raise RuntimeError('Existing probe: inspect, do not retry implicitly')
    for path,digest in manifest['classes'].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest
    for case in manifest['cases']:
        for prefix in ['','padded_']:
            assert hashlib.sha256((ROOT/case[prefix+'path']).read_bytes()).hexdigest()==case[prefix+'sha256']
    append(output,dict(type='metadata',manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        config=dict(context=768,output=128,threads=4),candidate=manifest['candidate'],acceptance=manifest['acceptance']))
    protocol=Protocol();model=runtime();rows=[]
    try:
        for index,case in enumerate(manifest['cases']):
            for mode in (['original','leading2s'] if index%2==0 else ['leading2s','original']):
                input_case={**case,'path':case['padded_path'] if mode=='leading2s' else case['path']}
                row=infer(model,protocol,input_case,'bilingual','');row['input_mode']=mode
                rows.append(row);append(output,dict(type='request',**row))
        append(output,dict(type='complete',requests=len(rows)))
    finally:
        model.close();protocol.close()
    summarize(manifest,rows)


if __name__=='__main__':
    if sys.argv[1:] == ['prepare']:
        prepare()
    elif sys.argv[1:] == ['run']:
        run()
    else:
        raise SystemExit('Usage: prepare|run')
