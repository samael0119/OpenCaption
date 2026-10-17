"""Offline-only FLEURS prefix qualification; no inference entry point."""
import csv
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tarfile
import wave

OLD = Path('evaluation/results/v020-independent/fleurs_preflight')
OUT = Path('evaluation/results/v020-evidence11')
MEMBER_MAX = 4 * 1024 * 1024
OUTPUT_MAX = 64 * 1024 * 1024


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''):
            h.update(b)
    return h.hexdigest()


def save(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def metadata(path):
    rows = []
    with Path(path).open() as f:
        for r in csv.reader(f, delimiter='\t'):
            if len(r) == 7 and r[0].isdigit() and r[5].isdigit():
                rows.append(dict(id=int(r[0]), filename=r[1], reference=r[2],
                                 samples=int(r[5]), gender=r[6]))
    return rows


def eligible(en, zh, excluded):
    refs = {}
    english_refs = {}
    for r in en:
        english_refs.setdefault(r['id'], set()).add(r['reference'])
    for r in zh:
        refs.setdefault(r['id'], set()).add(r['reference'])
    return sorted([dict(r, reference_en=r['reference'], reference_zh=next(iter(refs[r['id']])))
                   for r in en if r['id'] not in excluded and 16000 <= r['samples'] <= 80000
                   and len(refs.get(r['id'], ())) == 1
                   and len(english_refs[r['id']]) == 1
                   and re.fullmatch(r'\d+\.wav', r['filename'])],
                  key=lambda r: (r['id'], r['filename']))


def safe_member(m):
    p = PurePosixPath(m.name)
    return (m.isfile() and not p.is_absolute() and '..' not in p.parts
            and '\\' not in m.name and 0 < m.size <= MEMBER_MAX)


def scan(stream, wanted):
    """Only fully read members qualify; gzip EOF is explicitly incomplete archive."""
    found, seen, rejected = {}, set(), []
    error = None
    complete = 0
    try:
        with tarfile.open(fileobj=stream, mode='r|gz') as archive:
            for m in archive:
                name = PurePosixPath(m.name).name
                if not safe_member(m):
                    if m.isfile():
                        rejected.append(dict(name=m.name, reason='unsafe_or_oversize'))
                    continue
                # Stream every regular payload to distinguish complete vs partial.
                f = archive.extractfile(m)
                data = f.read(m.size + 1)
                if len(data) != m.size:
                    raise EOFError('Incomplete member: ' + m.name)
                complete += 1
                if name not in wanted:
                    continue
                if name in seen:
                    raise ValueError('Duplicate eligible archive basename: ' + name)
                seen.add(name)
                found[name] = dict(data=data, member=m.name, bytes=m.size)
    except (EOFError, tarfile.ReadError, OSError) as e:
        error = dict(type=type(e).__name__, message=str(e), expected_prefix_truncation=True)
    return found, dict(complete_regular_members=complete, matched_complete_members=len(found),
                       unsafe_or_oversize=rejected, archive_end_error=error,
                       full_archive_integrity_verified=error is None)


def freeze():
    if (OUT / 'manifest.json').exists():
        raise RuntimeError('Already frozen; no implicit retry')
    plan = json.loads((OLD / 'control_plan.json').read_text())
    ids = {x['id'] for x in plan['cases']}
    request_files = {}
    # Exclude every numeric case_id observed in local request logs, not outputs.
    for p in sorted(Path('evaluation/results').rglob('*requests*.jsonl')):
        request_files[str(p)] = sha(p)
        for line in p.open():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            for key in ('case_id', 'case', 'id'):
                v = r.get(key)
                if isinstance(v, int) or isinstance(v, str) and v.isdigit():
                    ids.add(int(v))
    audio_hashes = {}
    # All previously available FLEURS originals and converted variants are excluded.
    for folder in ('original', 'audio'):
        for p in sorted((OLD / folder).glob('*.wav')):
            audio_hashes[str(p)] = sha(p)
            if folder == 'audio':
                with wave.open(str(p), 'rb') as w:
                    audio_hashes[str(p) + ':pcm'] = sha_bytes(w.readframes(w.getnframes()))
    inputs = {str(OLD / n): sha(OLD / n) for n in
              ('archive_prefix.bin', 'en_test.tsv', 'zh_test.tsv', 'control_plan.json',
               'metadata_manifest.json', 'source_qualification.json')}
    for name, expected in plan['metadata_files'].items():
        if sha(OLD / name) != expected:
            raise RuntimeError('Original metadata mismatch: ' + name)
    save('exclusions.json', dict(ids=sorted(ids), request_files=request_files,
                                 old_audio_hashes=audio_hashes,
                                 note='Numeric request case IDs conservatively excluded; raw content not used to select.'))
    save('manifest.json', dict(inputs=inputs, exclusions_sha256=sha(OUT / 'exclusions.json'),
         revision=plan['revision'], license=plan['license'], repository=plan['repository'],
         max_cases=24, max_member_bytes=MEMBER_MAX, max_output_bytes=OUTPUT_MAX,
         selection='Complete7 columns; shared unique human references;1-5s; sorted(id,filename); first available filename per new ID; no outputs consulted.',
         source_sha256=sha(__file__), model_requests=0, network_requests=0,
         preparation_is_not_complete_round=True))


def prepare():
    if (OUT / 'qualification.json').exists():
        raise RuntimeError('Scan already completed; do not repeat')
    manifest = json.loads((OUT / 'manifest.json').read_text())
    for name, expected in manifest['inputs'].items():
        if sha(name) != expected:
            raise RuntimeError('Frozen input changed')
    ex = json.loads((OUT / 'exclusions.json').read_text())
    rows = eligible(metadata(OLD / 'en_test.tsv'), metadata(OLD / 'zh_test.tsv'), set(ex['ids']))
    with (OLD / 'archive_prefix.bin').open('rb') as f:
        found, summary = scan(f, {r['filename'] for r in rows})
    selected, used_ids, consumed = [], set(), 0
    for r in rows:
        name = r['filename']
        if name not in found or r['id'] in used_ids or len(selected) >= 24:
            continue
        d = found[name]
        if sha_bytes(d['data']) in ex['old_audio_hashes'].values():
            raise RuntimeError('Previously observed audio content')
        # Validate float32 or PCM WAV independently via ffprobe, before conversion.
        original = OUT / 'original' / name
        original.parent.mkdir(exist_ok=True)
        original.write_bytes(d['data'])
        info = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams',
                           '-of', 'json', str(original)], timeout=10))['streams']
        if len(info) != 1 or info[0]['sample_rate'] != '16000' or info[0]['channels'] != 1:
            raise RuntimeError('Original format mismatch')
        target = OUT / 'audio' / name
        target.parent.mkdir(exist_ok=True)
        subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-threads', '1', '-i', str(original),
                        '-c:a', 'pcm_s16le', str(target)], check=True, timeout=10)
        with wave.open(str(target), 'rb') as w:
            if w.getparams()[:3] != (1, 2, 16000) or w.getnframes() != r['samples']:
                raise RuntimeError('Metadata/sample count mismatch')
            pcm_hash = sha_bytes(w.readframes(w.getnframes()))
        if pcm_hash in ex['old_audio_hashes'].values():
            raise RuntimeError('Old PCM under new filename')
        consumed += original.stat().st_size + target.stat().st_size
        if consumed > OUTPUT_MAX:
            raise RuntimeError('Output budget exceeded')
        used_ids.add(r['id'])
        selected.append(dict(r, original_path=str(original), original_sha256=sha(original),
                             audio_path=str(target), audio_sha256=sha(target), pcm_sha256=pcm_hash,
                             archive_member=d['member'], reference_source='Publisher human parallel reference; no AI rewrite'))
    save('qualification.json', dict(**summary, eligible_metadata_rows=len(rows), selected=selected,
         selected_cases=len(selected), selected_seconds=sum(x['samples'] for x in selected) / 16000,
         new_audio_bytes=consumed, model_requests=0, network_requests=0,
         source_is_independent_CS2=False,
         reference_rating_by_AI_not_independent_human=True))
    print(json.dumps(dict(selected=len(selected), complete_members=summary['complete_regular_members'],
                          metadata_rows=len(rows), seconds=sum(x['samples'] for x in selected)/16000,
                          output_bytes=consumed, archive_end_error=summary['archive_end_error'])))


if __name__ == '__main__':
    OUT.mkdir(exist_ok=True)
    {'freeze': freeze, 'prepare': prepare}[sys.argv[1]]()
