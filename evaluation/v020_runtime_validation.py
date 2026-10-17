"""Bounded local controls + 3 real-clock resource runs, one model at a time.

Uses actual Kotlin prompt/parser. Public cases are independent of our tuning,
but one read-speech speaker and no Chinese/CS2 gold: do not claim full gates.
Long runs test Linux inference resources, not Android ANR or natural quality.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import resource
import statistics
import subprocess
import time
from types import SimpleNamespace

from gemma_replay import LiteRtRuntime
from score_reference import words, edit_distance
from v020_bridge_transport import split_response

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evaluation/results/v020-independent'
MODEL=Path('/home/hyh/Tools/litert/models/gemma-4-E2B-it.litertlm')


def append(path,row):
    with path.open('a') as f: f.write(json.dumps(row,ensure_ascii=False)+'\n')


def b64(value):return base64.b64encode(value.encode()).decode()
def un64(value):return base64.b64decode(value).decode()


class Protocol:
    def __init__(self):
        cp=(ROOT/'evaluation/results/v020-jvm/protocol-classpath.txt').read_text()
        self.process=subprocess.Popen(['/home/hyh/Tools/java/eclipse-temurin-jdk17/bin/java','-Xmx64m','-cp',cp,'V020ProtocolBridge'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    def send(self,command,task,value):
        self.process.stdin.write(f'{command}\t{task}\t{b64(value)}\n');self.process.stdin.flush()
        return split_response(self.process.stdout.readline())
    def prompt(self,task,hints):return tuple(map(un64,self.send('prompt',task,hints)))
    def parse(self,task,raw):
        fields=self.send('parse',task,raw)
        return dict(status=fields[0],english=un64(fields[1]) if fields[0]=='subtitle' else '',
            chinese=un64(fields[2]) if fields[0]=='subtitle' else '',
            reason=un64(fields[1]) if fields[0]=='invalid' else '')
    def close(self):
        self.process.stdin.close();self.process.wait(timeout=10)


def runtime():
    return LiteRtRuntime(SimpleNamespace(model=MODEL,threads=4,max_new_tokens=128,hints='',
        task='bilingual',task_profile='baseline',system_profile='minimal',cache_mode='disk',
        speculative_decoding='default',max_context_tokens=768))


def infer(model,protocol,case,task,hints):
    model.system_message,model.prompt=protocol.prompt(task,hints)
    began=time.monotonic()
    raw=model.infer(ROOT/case['path'])
    ms=(time.monotonic()-began)*1000
    parsed=protocol.parse(task,raw)
    return dict(case_id=case['id'],kind=case['kind'],task=task,hints=hints,inference_ms=ms,
        raw=raw,**parsed,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)


def controls():
    output=OUT/'controls.jsonl'
    if output.exists():raise RuntimeError('Controls already started; inspect checkpoint instead of rerunning')
    manifest=json.loads((OUT/'frozen_cases.json').read_text())
    cases=manifest['cases'];protocol=Protocol()
    append(output,dict(type='metadata',utc=datetime.now(timezone.utc).isoformat(),model_sha256=hashlib.sha256(MODEL.read_bytes()).hexdigest(),
        config=dict(context=768,output=128,threads=4),scope='English reference only; no CS2 or Chinese quality gate'))
    model=runtime()
    try:
        # Two directions per paired case, fixed before seeing model outputs.
        for index,case in enumerate(cases):
            for hints in (['','CS2 broadcast.'] if index%2==0 else ['CS2 broadcast.','']):
                row=infer(model,protocol,case,'bilingual',hints)
                append(output,dict(type='request',**row))
        music=[c for c in cases if c['kind']=='instrumental_music']
        for task in ['english','chinese','auto_zh']:
            for case in music:
                append(output,dict(type='request',**infer(model,protocol,case,task,'CS2 broadcast.')))
        append(output,dict(type='complete',utc=datetime.now(timezone.utc).isoformat()))
    finally:model.close();protocol.close()
    summarize()


def summarize():
    manifest=json.loads((OUT/'frozen_cases.json').read_text());cases={c['id']:c for c in manifest['cases']}
    rows=[json.loads(line) for line in (OUT/'controls.jsonl').read_text().splitlines()]
    result={'complete':rows[-1]['type']=='complete','scope':'one read-speech speaker; synthetic attenuation/mixes; no independent Chinese or CS2 gold','groups':{}}
    requests=[r for r in rows if r['type']=='request']
    for kind in sorted({r['kind'] for r in requests}):
        for hints in ['','CS2 broadcast.']:
            selected=[r for r in requests if r['kind']==kind and r['hints']==hints and r['task']=='bilingual']
            if not selected:continue
            refs=[words(cases[r['case_id']]['reference_en']) for r in selected]
            total=sum(len(ref) for ref in refs)
            errors=sum(edit_distance(ref,words(r['english'])) for r,ref in zip(selected,refs))
            result['groups'][kind+'|'+hints]=dict(n=len(selected),statuses={s:sum(r['status']==s for r in selected) for s in ['subtitle','no_speech','invalid']},
                reference_words=total,wer=errors/total if total else None,median_ms=statistics.median(r['inference_ms'] for r in selected))
    result['music_all_tasks']=[dict(case_id=r['case_id'],task=r['task'],status=r['status'],raw=r['raw']) for r in requests if r['kind']=='instrumental_music']
    (OUT/'controls_summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='music_all_tasks'},ensure_ascii=False),flush=True)


def stability(run,seconds):
    if seconds!=3600:raise ValueError('Acceptance runs require exactly 3600 real-clock input seconds')
    output=OUT/f'stability_{run}.jsonl'
    if output.exists():raise RuntimeError('Run already started; inspect completion before retry')
    manifest=json.loads((OUT/'frozen_cases.json').read_text())
    # Whole <=5s public fixtures paced at 5s. This is resource stress, not a
    # continuous natural stream or product queue/automatic-scene acceptance.
    cases=manifest['cases'];protocol=Protocol();model=runtime()
    origin=time.monotonic();deadline=origin+seconds
    append(output,dict(type='metadata',run=run,input_seconds=seconds,origin_monotonic=origin,
        utc=datetime.now(timezone.utc).isoformat(),scope='Linux inference resources; paced known clips; no quality generalization/Android/queue claim'))
    requests=0;missed_slots=0;max_lag=0;rss=[]
    try:
        slot=0
        while True:
            target=origin+(slot+1)*5
            if target>deadline:break
            remaining=target-time.monotonic()
            if remaining>0:time.sleep(remaining) # <=5s, real clock
            else:missed_slots+=1
            now=time.monotonic();max_lag=max(max_lag,now-target)
            hints='CS2 broadcast.' if (slot+1)%4==0 else ''
            case=cases[slot%len(cases)]
            row=infer(model,protocol,case,'bilingual',hints);requests+=1;rss.append(row['peak_rss_kib'])
            append(output,dict(type='request',slot=slot,target_monotonic=target,began_monotonic=now,
                lag_ms=(now-target)*1000,**row));slot+=1
        append(output,dict(type='complete',run=run,requests=requests,input_seconds=seconds,
            actual_elapsed_seconds=time.monotonic()-origin,missed_slots=missed_slots,max_lag_ms=max_lag*1000,
            peak_rss_kib=max(rss),utc=datetime.now(timezone.utc).isoformat()))
    finally:model.close();protocol.close()
    print(f'stability {run} complete: requests={requests}, max_lag_ms={max_lag*1000:.1f}',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('phase',choices=['controls','summary','stability']);parser.add_argument('--run',type=int);parser.add_argument('--seconds',type=int,default=3600)
    args=parser.parse_args()
    if args.phase=='controls':controls()
    elif args.phase=='summary':summarize()
    else:stability(args.run,args.seconds)
