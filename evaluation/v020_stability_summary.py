"""Inspect real-clock logs without rerunning inference or accepting partial runs."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import statistics


def rows_at(path):
    # An in-flight append may end midway through a JSON row. Never repair it.
    data = path.read_text()
    lines = data.splitlines()
    partial = bool(data and not data.endswith('\n'))
    if partial:
        lines = lines[:-1]
    return [json.loads(line) for line in lines], partial


def percentile(values, fraction):
    values = sorted(values)
    return values[max(0, math.ceil(len(values) * fraction) - 1)] if values else None


def summarize(rows, partial=False):
    metadata = [r for r in rows if r['type'] == 'metadata']
    requests = [r for r in rows if r['type'] == 'request']
    completions = [r for r in rows if r['type'] == 'complete']
    issues = []
    if len(metadata) != 1 or not rows or rows[0]['type'] != 'metadata':
        issues.append('metadata_missing_or_duplicated')
    if partial:
        issues.append('inflight_partial_row')
    slots = [r['slot'] for r in requests]
    if slots != list(range(len(slots))):
        issues.append('slots_not_contiguous')
    origin = metadata[0].get('origin_monotonic') if metadata else None
    if origin is not None:
        for row in requests:
            if abs(row['target_monotonic'] - origin - (row['slot'] + 1) * 5) > .001:
                issues.append('target_schedule_mismatch')
                break
    finished = len(completions) == 1 and bool(rows) and rows[-1]['type'] == 'complete'
    if not finished:
        issues.append('run_not_complete')
    else:
        end = completions[0]
        if (len(requests) != 720 or end.get('requests') != 720 or
                end.get('input_seconds') != 3600 or
                not math.isfinite(end.get('actual_elapsed_seconds', float('nan'))) or
                end.get('actual_elapsed_seconds', 0) < 3600):
            issues.append('not_720_slots_over_60_real_minutes')
        if metadata and metadata[0].get('input_seconds') != 3600:
            issues.append('metadata_duration_mismatch')
    inference = [r['inference_ms'] for r in requests]
    music = [r for r in requests if r['kind'] == 'instrumental_music']
    return dict(complete=finished, integrity_pass=finished and not issues, issues=issues,
                requests=len(requests), unique_cases=len({r['case_id'] for r in requests}),
                actual_elapsed_seconds=completions[0].get('actual_elapsed_seconds') if finished else None,
                statuses=dict(Counter(r['status'] for r in requests)),
                median_inference_ms=statistics.median(inference) if inference else None,
                p95_inference_ms=percentile(inference, .95),
                p99_inference_ms=percentile(inference, .99),
                max_lag_ms=max((r['lag_ms'] for r in requests), default=None),
                peak_rss_kib=max((r['peak_rss_kib'] for r in requests), default=None),
                music_requests=len(music),
                music_visible_hallucinations=sum(r['status'] == 'subtitle' for r in music),
                music_invalid=sum(r['status'] == 'invalid' for r in music),
                scope='Repeated known clips, Linux resource subexperiment; no product queue/scene/UI or independent quality acceptance')


def resources(rows):
    by_pid = {}
    for row in rows:
        if row['type'] == 'sample':
            by_pid.setdefault(str(row['pid']), []).append(row)
    result = {}
    for pid, samples in by_pid.items():
        rss = [r['rss_kib'] for r in samples if r.get('rss_kib') is not None]
        result[pid] = dict(samples=len(samples), sampled_seconds=samples[-1]['monotonic']-samples[0]['monotonic'],
                          first_rss_kib=rss[0] if rss else None, last_rss_kib=rss[-1] if rss else None,
                          min_rss_kib=min(rss) if rss else None, max_rss_kib=max(rss) if rss else None,
                          swap_seen=any(r.get('swap_kib', 0) or r.get('memory_swap_current_bytes', 0) for r in samples),
                          hard_limits_ok=all(r['memory_max_bytes']==6144*1024**2 and r['memory_swap_max_bytes']==0 for r in samples),
                          oom_kill_max=max(r['events'].get('oom_kill', 0) for r in samples))
    return dict(processes=result, sampling_errors=sum(r['type']=='sample_error' for r in rows),
                scope='Run 1 baseline is incomplete; RSS change alone does not diagnose a leak')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, default=Path(__file__).parent/'results/v020-independent')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = {'runs': {}}
    for run in range(1, 4):
        path = args.directory/f'stability_{run}.jsonl'
        result['runs'][str(run)] = summarize(*rows_at(path)) if path.exists() else {'complete': False, 'issues': ['not_started']}
    monitor = args.directory/'resource_samples.jsonl'
    if monitor.exists():
        result['resources'] = resources(rows_at(monitor)[0])
    result['three_resource_runs_complete'] = all(r.get('integrity_pass', False) for r in result['runs'].values())
    result['product_acceptance_complete'] = False
    value = json.dumps(result, ensure_ascii=False, indent=2)+'\n'
    if args.output:
        args.output.write_text(value)
    print(value, end='')


if __name__ == '__main__':
    main()
