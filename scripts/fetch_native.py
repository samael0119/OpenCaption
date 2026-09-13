#!/usr/bin/env python3
"""Fetch only the pinned source archives. Never download model weights implicitly."""
import io
import json
from pathlib import Path
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
for name, spec in json.loads((ROOT / 'native.lock.json').read_text()).items():
    if isinstance(spec, str):
        owner, commit = 'ggml-org', spec
    else:
        owner, commit = spec['owner'], spec['commit']
    dest = ROOT / 'third_party' / name
    marker = dest / '.opencaption-revision'
    git_head = dest / '.git' / 'HEAD'
    if marker.exists() and marker.read_text().strip() == commit:
        print(f'{name}: already pinned')
        continue
    if git_head.exists():
        revision = subprocess.check_output(
            ['git', '-C', str(dest), 'rev-parse', 'HEAD'], text=True,
        ).strip()
        if revision == commit:
            print(f'{name}: already pinned (git checkout)')
            continue
    if dest.exists():
        raise SystemExit(f'{dest} exists with a different revision; move it aside first')
    url = f'https://codeload.github.com/{owner}/{name}/tar.gz/{commit}'
    with urllib.request.urlopen(url, timeout=120) as response:
        data = response.read()
    dest.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        for member in archive.getmembers():
            parts = Path(member.name).parts[1:]
            if not parts:
                continue
            if '..' in parts or member.issym() or member.islnk():
                continue
            target = dest.joinpath(*parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.extractfile(member).read())
    marker.write_text(commit + '\n')
    print(f'{name}: {commit}')
