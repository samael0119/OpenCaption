"""Deterministic local queue replay using measured CPU service-time traces.

Virtual clock/fault injection, not a new model or OS-load benchmark. Capture
arrivals are causal cut endpoints; complete events precede simultaneous cuts.
"""
from dataclasses import dataclass
import json

from s0_probe import OUT as S0, write_json

OUT = S0/'local_followup'


@dataclass(frozen=True)
class Segment:
    id: int
    start_ms: float
    end_ms: float
    service_ms: float


def replay(segments, max_age_ms=2500, extra_service=None):
    active = pending = None
    delivered, dropped, starts = [], [], []
    max_pending = 0
    def start(segment, now):
        age=now-segment.end_ms
        assert 0<=age<=max_age_ms
        extra=(extra_service(segment) if extra_service else 0)
        if extra<0:raise ValueError('Negative delay')
        starts.append(dict(id=segment.id,start_clock_ms=now,audio_age_ms=age))
        return (segment,now,now+segment.service_ms+extra,extra)
    def finish_one():
        nonlocal active,pending
        segment,began,finished,extra=active
        delivered.append(dict(id=segment.id,start_ms=segment.start_ms,end_ms=segment.end_ms,
            started_ms=began,completed_ms=finished,service_ms=segment.service_ms,
            injected_ms=extra,queue_age_ms=began-segment.end_ms))
        active=None
        if pending:
            waiting=pending;pending=None
            if finished-waiting.end_ms>max_age_ms:
                dropped.append(dict(id=waiting.id,start_ms=waiting.start_ms,end_ms=waiting.end_ms,
                    reason='expired',clock_ms=finished,age_ms=finished-waiting.end_ms))
            else:
                active=start(waiting,finished)
    previous_end=0
    for segment in segments:
        if segment.start_ms!=previous_end or not 0<segment.end_ms-segment.start_ms<=5000 or segment.service_ms<0:
            raise ValueError('Noncontinuous PCM or invalid service time')
        previous_end=segment.end_ms
        now=segment.end_ms
        while active and active[2]<=now:
            finish_one()
        if active is None:
            active=start(segment,now)
        else:
            if pending:
                dropped.append(dict(id=pending.id,start_ms=pending.start_ms,end_ms=pending.end_ms,
                    reason='replaced',clock_ms=now,age_ms=now-pending.end_ms))
            pending=segment
            max_pending=max(max_pending,1)
    while active:
        finish_one()
    assert pending is None
    ids=[r['id'] for r in delivered+dropped]
    assert len(ids)==len(set(ids))==len(segments)
    assert set(ids)=={s.id for s in segments}
    assert sum(r['end_ms']-r['start_ms'] for r in delivered+dropped)==previous_end
    assert all(a['completed_ms']<=b['started_ms'] for a,b in zip(delivered,delivered[1:]))
    return dict(delivered=delivered,dropped=dropped,starts=starts,
                max_pending=max_pending,age_limit_ms=max_age_ms)


def run():
    rows=[json.loads(s) for s in (S0/'protocol_live/paced.jsonl').read_text().splitlines()]
    assert rows[-1]['type']=='complete'
    result=dict(kind='virtual-clock queue/fault replay, not measured inference under contention',
        age_definition='Audio chunk end to inference start; cap 2500ms is a test parameter, not product default',
        fault='Add 4000ms service delay to segments ending at or before 30000ms, then remove it',policies={})
    for policy in ['fixed_5000','pause_600_max_5000']:
        selected=[r for r in rows if r.get('policy')==policy and r['type']=='delivered']
        segments=[Segment(r['id'],r['start_ms'],r['end_ms'],r['inference_ms']) for r in selected]
        result['policies'][policy]={}
        for mode in ['normal','slow_first_30s']:
            replayed=replay(segments,extra_service=(lambda s:4000 if s.end_ms<=30000 else 0)
                            if mode=='slow_first_30s' else None)
            replayed.update(submitted=len(segments),delivered_n=len(replayed['delivered']),
                dropped_n=len(replayed['dropped']),dropped_ms=sum(r['end_ms']-r['start_ms'] for r in replayed['dropped']),
                max_started_age_ms=max(r['queue_age_ms'] for r in replayed['delivered']),
                delivered_after_40s=sum(r['end_ms']>40000 for r in replayed['delivered']),
                submitted_after_40s=sum(s.end_ms>40000 for s in segments))
            result['policies'][policy][mode]=replayed
    write_json(OUT/'queue_stress.json',result)
    for policy,modes in result['policies'].items():
        for mode,value in modes.items():
            print(policy,mode,{k:v for k,v in value.items() if k not in ['delivered','dropped','starts']})


if __name__=='__main__':
    run()
