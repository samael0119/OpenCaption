"""One finite negative control of proactive hints on 12 unseen speakers.

No CS2 quality claim: ordinary keyword labels test false entity injection and
protocol/cost regression, not positive terminology or scene net benefit.
"""
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


def digest(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()


def prepare():
    manifest=OUT/'related_keyword_manifest.json'
    if manifest.exists(): raise RuntimeError('Already frozen; no re-selection')
    prompts=json.loads((OUT/'related_prompt_snapshot.json').read_text())
    excluded=set()
    for name in ['short_answer_cases.json','short_padding_manifest.json']:
        excluded.update(c['speaker_id'] for c in json.loads((OUT/name).read_text())['cases'])
    speakers=set(excluded); assets=OUT/'related_keyword_guard'; assets.mkdir(exist_ok=False)
    cases=[]
    with tarfile.open(ARCHIVE,'r:gz') as archive:
        members=sorted((m for m in archive if m.isfile()),key=lambda m:m.name)
        for label in ['no','yes','six','two','nine','four']:
            selected=0
            for member in members:
                match=re.fullmatch(r'(?:(\w+)_)?([0-9a-f]{8})_nohash_(\d+)\.wav(?:\.wav)?',Path(member.name).name)
                if not match: continue
                source_label=match.group(1) or Path(member.name).parent.name
                speaker=match.group(2)
                if source_label!=label or speaker in speakers: continue
                original=archive.extractfile(member).read()
                with wave.open(io.BytesIO(original)) as w:
                    assert (w.getnchannels(),w.getsampwidth(),w.getframerate())==(1,2,16000)
                    samples=w.getnframes();pcm=w.readframes(samples)
                assert 0<samples<=17600
                speakers.add(speaker); ident=f'{label}-{speaker}-{match.group(3)}'
                raw=assets/(ident+'.wav'); raw.write_bytes(original)
                padded=assets/(ident+'-leading2s.wav')
                with wave.open(str(padded),'wb') as w:
                    w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000)
                    w.writeframes(bytes((32000-samples)*2)+pcm)
                with wave.open(str(padded)) as w: actual=w.readframes(w.getnframes())
                assert len(actual)==64000 and actual[-len(pcm):]==pcm and not any(actual[:-len(pcm)])
                cases.append(dict(id=ident,kind='public_single_keyword',label=label,reference_en=label,
                    reference_zh_options=LABELS[label],speaker_id=speaker,source_member=member.name,
                    source_samples=samples,path=str(padded.relative_to(ROOT)),sha256=digest(padded),
                    original_path=str(raw.relative_to(ROOT)),original_sha256=digest(raw)))
                selected+=1
                if selected==2: break
            assert selected==2,label
    native=json.loads((OUT/'controller_closed_loop_manifest.json').read_text())['classes']
    for p,h in native.items(): assert digest(ROOT/p)==h
    meta=dict(frozen_utc=datetime.now(timezone.utc).isoformat(),cases=cases,classes=native,
        prompts=prompts,prior_speakers_excluded=sorted(excluded),new_speakers=12,
        model_sha256=digest('/home/hyh/Tools/litert/models/gemma-4-E2B-it.litertlm'),
        source_url='https://storage.googleapis.com/download.tensorflow.org/data/speech_commands_test_set_v0.02.tar.gz',
        source_archive_sha256=digest(ARCHIVE),license='CC BY 4.0',attribution='Speech Commands Test Files v0.02, Pete Warden / Google',
        selection='First two filename-sorted globally unseen speaker IDs for no,yes,six,two,nine,four; exclude all previous 72; no output-based selection',
        input='Common E2B product 2s leading-zero floor in both modes; original samples unchanged',
        config=dict(context=768,output=128,threads=4,task='bilingual'),
        acceptance=dict(no_new_no_speech=True,no_new_invalid=True,no_source_regression=True,
            no_joint_regression=True,no_candidate_entity_insertion=True,max_median_ratio=1.3,max_p95_ms=3000),
        scope='Negative keyword control only; constructed prior Nuke scene deliberately unrelated. Same frozen templates, direct hint use bypasses cadence. No CS2 term gain/scene/Chinese-sentence gold or device claim; pretraining contamination unknown.')
    manifest.write_text(json.dumps(meta,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(cases=12,prior_speakers=len(excluded),requests=24),ensure_ascii=False))


def run():
    path=OUT/'related_keyword_manifest.json'; m=json.loads(path.read_text()); output=OUT/'related_keyword_guard.jsonl'
    if output.exists(): raise RuntimeError('Already started; no implicit retry')
    phases=[json.loads(line) for line in (OUT/'related_fixed_pipeline.jsonl').read_text().splitlines()]
    assert len(phases)==5 and all(row['exit_code']==0 for row in phases), 'Wait for build exit/success'
    for p,h in m['classes'].items(): assert digest(ROOT/p)==h
    assert digest('/home/hyh/Tools/litert/models/gemma-4-E2B-it.litertlm')==m['model_sha256']
    for case in m['cases']:
        assert digest(ROOT/case['path'])==case['sha256']
        assert digest(ROOT/case['original_path'])==case['original_sha256']
    from v020_runtime_validation import Protocol,runtime,infer,append
    from v020_short_answer_validation import score
    append(output,dict(type='metadata',manifest_sha256=digest(path),scope=m['scope'],config=m['config']))
    protocol=Protocol();model=runtime();rows=[]
    try:
        for index,case in enumerate(m['cases']):
            order=['baseline','related'] if index%2==0 else ['related','baseline']
            for mode in order:
                row=infer(model,protocol,case,'bilingual',m['prompts'][mode]);row['mode']=mode
                row.update(score(row,case))
                row['candidate_entity_inserted']=bool(re.search(r'\bsecret\b|\bb site\b',row.get('english',''),re.I) or
                    re.search(r'地下通道|B包点',row.get('chinese',''),re.I))
                rows.append(row);append(output,dict(type='request',**row))
        append(output,dict(type='complete',requests=len(rows),utc=datetime.now(timezone.utc).isoformat()))
    finally: model.close();protocol.close()
    groups={};paired={}
    for mode in ['baseline','related']:
        selected=[r for r in rows if r['mode']==mode];times=sorted(r['inference_ms'] for r in selected)
        groups[mode]=dict(n=len(selected),statuses=dict(Counter(r['status'] for r in selected)),
            source_correct=sum(r['source_keyword_ok'] for r in selected),joint_correct=sum(r['joint_keyword_ok'] for r in selected),
            candidate_entity_insertions=sum(r['candidate_entity_inserted'] for r in selected),
            median_ms=statistics.median(times),p95_ms=times[math.ceil(.95*len(times))-1])
        paired[mode]={r['case_id']:r for r in selected}
    pairs=[]
    for case in m['cases']:
        a=paired['baseline'][case['id']];b=paired['related'][case['id']]
        pairs.append(dict(id=case['id'],label=case['label'],baseline_status=a['status'],related_status=b['status'],
            source_regression=a['source_keyword_ok'] and not b['source_keyword_ok'],
            joint_regression=a['joint_keyword_ok'] and not b['joint_keyword_ok'],
            related_entity_inserted=b['candidate_entity_inserted']))
    checks=dict(no_new_no_speech=not any(p['baseline_status']!='no_speech' and p['related_status']=='no_speech' for p in pairs),
        no_new_invalid=not any(p['baseline_status']!='invalid' and p['related_status']=='invalid' for p in pairs),
        no_source_regression=not any(p['source_regression'] for p in pairs),
        no_joint_regression=not any(p['joint_regression'] for p in pairs),
        no_candidate_entity_insertion=not any(p['related_entity_inserted'] for p in pairs),
        median_ratio=groups['related']['median_ms']/groups['baseline']['median_ms']<=m['acceptance']['max_median_ratio'],
        p95=groups['related']['p95_ms']<=m['acceptance']['max_p95_ms'])
    (OUT/'related_keyword_summary.json').write_text(json.dumps(dict(complete=True,requests=len(rows),groups=groups,
        pairs=pairs,checks=checks,negative_guard_passed=all(checks.values()),product_enabled=False,
        scope=m['scope']),ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(groups=groups,checks=checks),ensure_ascii=False),flush=True)


if __name__=='__main__':
    if sys.argv[1:]==['prepare']: prepare()
    elif sys.argv[1:]==['run']: run()
    else: raise SystemExit('prepare or run')
