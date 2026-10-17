"""Bounded public-data preparation only; never loads a model or changes gold.

The selection is frozen in control_plan.json before audio retrieval/inference.
Underlying FLORES text is human-translated; recordings are publisher-validated
read speech, not independent CS2 broadcasts or a guarantee of semantic scoring.
"""
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import tarfile
import urllib.request
import wave
from datetime import datetime

OUT = Path('evaluation/results/v020-independent/fleurs_preflight')


class LimitedStream:
    def __init__(self, response, destination, limit):
        self.response, self.destination, self.limit = response, destination, limit
        self.count = 0
        self.digest = hashlib.sha256()

    def read(self, size):
        if not 0 < size <= 1048576 or self.count + size > self.limit:
            raise RuntimeError('Compressed archive read bound reached')
        data = self.response.read(size)
        self.destination.write(data)
        self.digest.update(data)
        self.count += len(data)
        return data


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for data in iter(lambda: source.read(1048576), b''):
            digest.update(data)
    return digest.hexdigest()


def main():
    plan = json.loads((OUT/'control_plan.json').read_text())
    prefix = OUT/'archive_prefix.bin'
    if prefix.exists() or (OUT/'audio_manifest.json').exists():
        raise RuntimeError('Preparation already started; inspect evidence, no implicit retry')
    for name, expected in plan['metadata_files'].items():
        if sha(OUT/name) != expected:
            raise RuntimeError('Frozen metadata changed')
    wanted = {x['filename']: x for x in plan['cases']}
    if len(wanted) != 12 or any(not n[:-4].isdigit() or not n.endswith('.wav') for n in wanted):
        raise RuntimeError('Invalid frozen case filenames')
    original = OUT/'original'; original.mkdir(exist_ok=True)
    prepared = OUT/'audio'; prepared.mkdir(exist_ok=True)
    began = datetime.now().astimezone().isoformat()
    stream = None; found = {}; header = {}
    try:
        request = urllib.request.Request(plan['archive']+'?download=true',
            headers={'User-Agent': 'OpenCaption-local-evaluation', 'Cache-Control': 'no-cache'})
        with urllib.request.urlopen(request, timeout=30) as response, prefix.open('wb') as output:
            header = dict(etag=response.headers.get('ETag'),content_length=response.headers.get('Content-Length'))
            stream = LimitedStream(response,output,plan['max_download_bytes'])
            with tarfile.open(fileobj=stream, mode='r|gz') as archive:
                for member in archive:
                    path = PurePosixPath(member.name)
                    if path.name not in wanted:
                        continue
                    if not member.isfile() or path.is_absolute() or '..' in path.parts or member.size > plan['max_member_bytes']:
                        raise RuntimeError('Invalid selected archive member')
                    if path.name in found:
                        raise RuntimeError('Duplicate selected member')
                    source = archive.extractfile(member)
                    data = source.read(plan['max_member_bytes']+1)
                    if len(data) != member.size:
                        raise RuntimeError('Incomplete archive member')
                    target = original/path.name
                    target.write_bytes(data)
                    found[path.name] = member.name
                    if len(found) == len(wanted):
                        break
        if set(found) != set(wanted):
            raise RuntimeError('Not all frozen cases found; do not replace missing cases')
        cases=[]
        for name, case in wanted.items():
            target=prepared/name
            subprocess.run(['ffmpeg','-nostdin','-v','error','-threads','1','-i',str(original/name),
                '-ac','1','-ar','16000','-c:a','pcm_s16le',str(target)],check=True,timeout=20)
            with wave.open(str(target),'rb') as audio:
                if audio.getparams()[:3] != (1,2,16000) or audio.getnframes() != case['samples']:
                    raise RuntimeError('Converted format/duration differs from frozen metadata')
                pcm=audio.readframes(audio.getnframes())
            cases.append({**case,'original_path':str(original/name),'original_sha256':sha(original/name),
                'path':str(target),'sha256':sha(target),'pcm_sha256':hashlib.sha256(pcm).hexdigest(),
                'archive_member':found[name],'conversion':'ffmpeg PCM s16le/mono/16k; no trimming/gain normalization'})
        manifest=dict(complete=True,began_at=began,finished_at=datetime.now().astimezone().isoformat(),
            plan_sha256=sha(OUT/'control_plan.json'),revision=plan['revision'],archive_url=plan['archive'],
            archive_prefix_bytes=stream.count,archive_prefix_sha256=stream.digest.hexdigest(),
            full_archive_integrity_verified=False,response_headers=header,cases=cases,
            scope=plan['scope'],inference_started=False)
        (OUT/'audio_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(dict(complete=True,cases=len(cases),audio_seconds=sum(x['samples'] for x in cases)/16000,
            downloaded_prefix_bytes=stream.count,inference_started=False)))
    except Exception as error:
        (OUT/'preparation_failure.json').write_text(json.dumps(dict(began_at=began,
            finished_at=datetime.now().astimezone().isoformat(),error=str(error),found_members=list(found),
            downloaded_prefix_bytes=stream.count if stream else 0,
            downloaded_prefix_sha256=stream.digest.hexdigest() if stream else None,
            scope='Incomplete preparation; no inference or quality claim'),ensure_ascii=False,indent=2)+'\n')
        raise


if __name__ == '__main__':
    main()
