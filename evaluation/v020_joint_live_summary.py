"""Audit real-clock ownership + core/widget transport, not audio quality."""
import argparse
import json
from pathlib import Path


def partition(intervals, end):
    previous = 0
    for a, b in sorted(intervals):
        if a != previous or not a < b <= end:
            raise ValueError('Missing/overlapping ownership interval')
        previous = b
    if previous != end:
        raise ValueError('Capture tail unaccounted')


def audit(model, ui, seconds):
    if model[-1]['type'] != 'complete' or ui[-1]['type'] != 'complete':
        raise ValueError('Incomplete run; never infer completion from file length')
    events = [x for x in model if x['type'] == 'capture_event']
    transported = [x for x in ui if x['type'] == 'capture_event']
    if [(x['event'], x['fields']) for x in events] != [(x['event'], x['fields']) for x in transported]:
        raise ValueError('Capture events lost in controller transport')
    ends = [x['fields'] for x in events if x['event'] == 'CAPEND']
    if len(ends) != 1 or int(ends[0][0]) != seconds*1000 or int(ends[0][1]) != seconds*50 or int(ends[0][3]) < seconds*1000:
        raise ValueError('Not the required real-clock capture')
    offers = [x['fields'] for x in events if x['event'] == 'OFFER']
    partition([(int(f[1]), int(f[2])) for f in offers], seconds*1000)
    if any(int(f[2])-int(f[1]) > 5000 or int(f[5]) > 1 for f in offers):
        raise ValueError('Capture/queue bound exceeded')
    results = [x for x in model if x['type'] == 'result']
    starts = [x for x in model if x['type'] == 'request_start']
    widgets = [x for x in ui if x['type'] == 'widget_result']
    ids = lambda rows: [x['window'] for x in rows]
    if len(set(ids(results))) != len(results) or ids(starts) != ids(results) or ids(widgets) != ids(results):
        raise ValueError('Duplicate/missing model or widget result')
    if model[-1]['requests'] != len(results) or ui[-1]['requests'] != len(results):
        raise ValueError('Incorrect final count')
    gaps = [x['fields'] for x in events if x['event'] == 'GAP']
    zero = [x['fields'] for x in events if x['event'] == 'ZERO']
    partition([(x['start_ms'], x['end_ms']) for x in results]
              +[(int(f[1]),int(f[2])) for f in gaps+zero], seconds*1000)
    for row in results:
        if not 0 <= row['started_ms']-row['submitted_ms'] <= 5000:
            raise ValueError('Stale queued service')
        if row['source_samples'] != (row['end_ms']-row['start_ms'])*16 or row['input_samples'] != max(32000,row['source_samples']):
            raise ValueError('Input ownership/padding mismatch')
    # The displayed text must preserve actual result/hint provenance; widget
    # corrections may differ in ledger text, but cannot fabricate raw output.
    for result, widget in zip(results, widgets):
        for key in ['window', 'raw', 'hints', 'status', 'start_ms', 'end_ms']:
            if result[key] != widget[key]: raise ValueError('Transport provenance mismatch')
        if widget['widget_exception']: raise ValueError('Widget exception')
    resources = [x['resources'] for x in events if x['event'] == 'ACT']
    if len(resources) != seconds or any(x['memory.swap.current']!='0' for x in resources):
        raise ValueError('Missing resources/swap used')
    oom = lambda x: int(dict(line.split() for line in x['memory.events'].splitlines())['oom_kill'])
    if any(oom(x)>0 for x in resources): raise ValueError('Observed OOMKill')
    return dict(complete=True, input_seconds=seconds, requests=len(results),
                offers=len(offers), queue_gaps=len(gaps), queue_gap_ms=sum(int(f[2])-int(f[1]) for f in gaps),
                merged_offers=sum(f[4]=='true' for f in offers), zero_filtered=len(zero),
                statuses={s:sum(x['status']==s for x in results) for s in ['subtitle','invalid','no_speech']},
                capture_max_lag_ms=float(ends[0][2]), actual_capture_elapsed_ms=int(ends[0][3]),
                peak_cgroup_bytes=max(int(x['memory.peak']) for x in resources),
                measured_screen_latency=False, independent_quality_acceptance=False,
                scope='Real JVM product cores, single model, real Dart controller and test widget; Android host not included')


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run'); args=parser.parse_args()
    out=Path('evaluation/results/v020-independent')
    if 'All tests passed!' not in (out/f'joint_live_{args.run}_test.log').read_text():
        raise ValueError('The integration test did not pass; JSON completion is insufficient')
    read=lambda suffix: [json.loads(x) for x in (out/f'joint_live_{args.run}_{suffix}.jsonl').read_text().splitlines()]
    seconds=json.loads((out/'joint_live_manifest.json').read_text())['runs'][args.run]['seconds']
    result=audit(read('model'), read('ui'), seconds)
    (out/f'joint_live_{args.run}_summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))
