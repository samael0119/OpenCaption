"""Bounded original Marian archive preparation, no translation requests."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import sys
import time
import urllib.request
import zipfile

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evaluation/results/v020-mt6'
URL='https://object.pouta.csc.fi/Tatoeba-MT-models/eng-zho/opus-2020-07-17.zip'
LIMIT=512*1024**2


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for c in iter(lambda:f.read(1048576),b''):h.update(c)
    return h.hexdigest()


def download():
    target=OUT/'opus-2020-07-17.zip';part=target.with_suffix('.zip.part')
    if target.exists() or part.exists():raise RuntimeError('Already downloaded/started; inspect, do not retry implicitly')
    start=time.monotonic();count=0
    with urllib.request.urlopen(URL,timeout=30) as response:
        headers=dict(response.headers)
        if int(headers.get('Content-Length',headers.get('content-length','0')))>LIMIT:raise RuntimeError('Archive exceeds frozen limit')
        (OUT/'download_headers.json').write_text(json.dumps(dict(url=URL,headers=headers),indent=2))
        with part.open('xb') as f:
            while True:
                if time.monotonic()-start>300:raise TimeoutError('Total download deadline')
                block=response.read(1048576)
                if not block:break
                count+=len(block)
                if count>LIMIT:raise RuntimeError('Download byte cap')
                f.write(block)
    part.rename(target)
    (OUT/'archive_provenance.json').write_text(json.dumps(dict(url=URL,bytes=count,sha256=sha(target),elapsed_seconds=time.monotonic()-start,upstream_signature_verified=False),indent=2))


def extract():
    target=OUT/'original'
    if target.exists():raise RuntimeError('Extraction already started')
    target.mkdir()
    inventory=[];total=0
    with zipfile.ZipFile(OUT/'opus-2020-07-17.zip') as z:
        for m in z.infolist():
            path=PurePosixPath(m.filename)
            if path.is_absolute() or '..' in path.parts or m.file_size>1024**3:raise RuntimeError('Unsafe archive member')
            total+=m.file_size
            if total>2*1024**3:raise RuntimeError('Expanded archive cap')
            p=target/path
            if m.is_dir():p.mkdir(parents=True,exist_ok=True);continue
            p.parent.mkdir(parents=True,exist_ok=True)
            with z.open(m) as source,p.open('xb') as dest:shutil.copyfileobj(source,dest,1048576)
            inventory.append(dict(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,sha256=sha(p)))
    (OUT/'original_inventory.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2))
    print(json.dumps(inventory,ensure_ascii=False,indent=2))


if __name__=='__main__':{'download':download,'extract':extract}[sys.argv[1]]()
