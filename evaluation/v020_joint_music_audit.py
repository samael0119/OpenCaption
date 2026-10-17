"""Inspect completed joint logs for outputs on known music-only PCM intervals.

Use the frozen playlist and sample coordinates, never the model transcript to
decide whether speech existed. Mixed speech/music boundaries are excluded.
Repeated old piano controls are not independent music-quality acceptance.
"""
import argparse
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import wave


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pieces(start, end, playlist, cycle_samples, music_paths):
    """Partition global sample interval, including cycle wraps and added zeros."""
    if not 0 <= start < end or cycle_samples <= 0:
        raise ValueError('Invalid interval')
    result = []
    cursor = start
    while cursor < end:
        local = cursor % cycle_samples
        item = next((item for item in playlist if item['start_sample'] <= local <
                     item['start_sample'] + item['samples'] + item['added_zero_samples']), None)
        if item is None:
            raise ValueError('Frozen playlist does not cover sample')
        audio_end = item['start_sample'] + item['samples']
        zero = local >= audio_end
        bound = audio_end + item['added_zero_samples'] if zero else audio_end
        count = min(end - cursor, bound - local, cycle_samples - local)
        if count <= 0:
            raise ValueError('Playlist boundary invalid')
        result.append(dict(start_sample=cursor, end_sample=cursor + count,
            cycle_start_sample=local, cycle_end_sample=local + count,
            path=item['path'], kind='added_zero' if zero else
                ('known_instrumental_music' if item['path'] in music_paths else 'speech_or_other')))
        cursor += count
    return result


def eligible(parts):
    return any(part['kind'] == 'known_instrumental_music' for part in parts) and all(
        part['kind'] in ['known_instrumental_music', 'added_zero'] for part in parts)


def main(run):
    root = Path(__file__).resolve().parents[1]
    out = root / 'evaluation/results/v020-independent'
    destination = out / f'joint_live_{run}_music_audit.json'
    if destination.exists():
        raise RuntimeError('Already audited; inspect saved output instead of implicit rewrite')
    read = lambda path: json.loads(path.read_text())
    manifest_path = out / 'joint_live_manifest.json'
    manifest = read(manifest_path)
    model_path = out / f'joint_live_{run}_model.jsonl'
    ui_path = out / f'joint_live_{run}_ui.jsonl'
    model = [json.loads(line) for line in model_path.read_text().splitlines()]
    ui = [json.loads(line) for line in ui_path.read_text().splitlines()]
    if model[0]['manifest_sha256'] != digest(manifest_path):
        raise ValueError('Run manifest changed')
    if 'All tests passed!' not in (out / f'joint_live_{run}_test.log').read_text():
        raise ValueError('Integration test incomplete/failed')
    from v020_joint_live_summary import audit
    summary = audit(model, ui, manifest['runs'][run]['seconds'])
    frozen_path = out / 'frozen_cases.json'
    music = {case['path']: case for case in read(frozen_path)['cases']
             if case['kind'] == 'instrumental_music' and case['expect_no_speech']}
    for item in manifest['playlist']:
        if item['path'] in music:
            case = music[item['path']]
            if item['sha256'] != case['sha256'] or item['samples'] != case['samples'] or digest(root / item['path']) != case['sha256']:
                raise ValueError('Known music fixture changed')
    cycle_path = out / 'joint_live_cycle.wav'
    if digest(cycle_path) != manifest['files'][str(cycle_path.relative_to(root))]:
        raise ValueError('Cycle PCM changed')
    with wave.open(str(cycle_path)) as wav:
        if (wav.getframerate(), wav.getnchannels(), wav.getsampwidth(), wav.getnframes()) != (16000, 1, 2, manifest['cycle_samples']):
            raise ValueError('Cycle format/length changed')
        pcm = wav.readframes(wav.getnframes())
    widgets = {row['window']: row for row in ui if row['type'] == 'widget_result'}
    results = []
    mixed = 0
    for row in model:
        if row['type'] != 'result':
            continue
        parts = pieces(row['start_ms']*16, row['end_ms']*16,
                       manifest['playlist'], manifest['cycle_samples'], music)
        if not eligible(parts):
            if any(part['kind'] == 'known_instrumental_music' for part in parts):
                mixed += 1
            continue
        # Distinguish nominal music intervals from exact-zero subsets.
        nonzero = any(any(pcm[part['cycle_start_sample']*2:part['cycle_end_sample']*2])
                      for part in parts if part['kind'] == 'known_instrumental_music')
        if not nonzero:
            continue
        widget = widgets[row['window']]
        results.append(dict(window=row['window'], start_ms=row['start_ms'], end_ms=row['end_ms'],
            parts=parts, nonzero=True, status=row['status'], raw=row['raw'],
            hints=row['hints'], verification=row['verification'],
            english=row['english'], chinese=row['chinese'],
            displayed_english=widget['displayed_english'], displayed_chinese=widget['displayed_chinese']))
    value = dict(checked_at=datetime.now().astimezone().isoformat(), run=run,
        mechanism_summary=summary, eligible_music_only_windows=len(results),
        mixed_speech_music_windows_excluded=mixed,
        statuses=dict(Counter(row['status'] for row in results)),
        visible_music_subtitles=sum(row['status'] == 'subtitle' for row in results),
        rows=results, original_music_clips=4, independent_music_sources=1,
        quality_gate_passed=False, quality_scope='Repeated four old nonzero piano controls, sample-exact music+added-zero intervals; not independent material, no positive acceptance claim. Subtitle on these intervals violates the zero-fabrication requirement.',
        screen_latency_measured=False,
        hashes={str(path.relative_to(root)): digest(path) for path in
                [manifest_path, frozen_path, cycle_path, model_path, ui_path]})
    with destination.open('x') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({key: val for key, val in value.items() if key not in ['rows', 'hashes']}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', choices=['run1', 'run2', 'run3'])
    main(parser.parse_args().run)
