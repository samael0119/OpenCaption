"""Freeze canonical public keyword labels before any model sees the clips."""
from array import array
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import re
import sys
import tarfile
import wave

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'evaluation/results/v020-independent'
ARCHIVE = OUT/'assets/speech_commands_test_v002.tar.gz'
LABELS = {
    'zero': ['0', '零'], 'one': ['1', '一'], 'two': ['2', '二', '两'],
    'three': ['3', '三'], 'four': ['4', '四'], 'five': ['5', '五'],
    'six': ['6', '六'], 'seven': ['7', '七'], 'eight': ['8', '八'],
    'nine': ['9', '九'], 'yes': ['是', '是的', '对', '好的', '好', '没错'],
    'no': ['不', '不是', '否', '不对', '不要', '不行', '没有'],
}


def main():
    manifest = OUT/'short_answer_cases.json'
    if manifest.exists():
        raise RuntimeError('Already frozen; do not reselect based on outputs')
    assets = OUT/'short_answers'
    assets.mkdir(exist_ok=True)
    cases, speakers = [], set()
    with tarfile.open(ARCHIVE, 'r:gz') as archive:
        members = sorted((m for m in archive if m.isfile()), key=lambda m:m.name)
        for label, chinese in LABELS.items():
            selected = 0
            for member in members:
                name = Path(member.name).name
                # Unknown-category files retain their original word prefix.
                match = re.fullmatch(r'(?:(\w+)_)?([0-9a-f]{8})_nohash_(\d+)\.wav(?:\.wav)?', name)
                if not match:
                    continue
                source_label = match.group(1) or Path(member.name).parent.name
                speaker = match.group(2)
                if source_label != label or speaker in speakers:
                    continue
                content = archive.extractfile(member).read()
                with wave.open(io.BytesIO(content)) as wav:
                    assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate()) == (1, 2, 16000)
                    samples = wav.getnframes()
                    pcm = array('h', wav.readframes(samples))
                    if sys.byteorder != 'little':
                        pcm.byteswap()
                assert 0 < samples <= 17600
                speakers.add(speaker)
                case_id = f'{label}-{speaker}-{match.group(3)}'
                path = assets/(case_id+'.wav')
                path.write_bytes(content)
                cases.append(dict(id=case_id, kind='public_single_keyword', path=str(path.relative_to(ROOT)),
                                  label=label, reference_en=label, reference_zh_options=chinese,
                                  source_member=member.name, speaker_id=speaker, samples=samples,
                                  duration_seconds=samples/16000, sha256=hashlib.sha256(content).hexdigest(),
                                  rms=math.sqrt(sum(x*x for x in pcm)/samples)/32768,
                                  peak=max(abs(x) for x in pcm)/32768))
                selected += 1
                if selected == 2:
                    break
            assert selected == 2, f'Missing two unique speakers: {label}'
    manifest.write_text(json.dumps(dict(
        frozen_utc=datetime.now(timezone.utc).isoformat(),
        source_url='https://storage.googleapis.com/download.tensorflow.org/data/speech_commands_test_set_v0.02.tar.gz',
        attribution='Speech Commands Test Files v0.02, Pete Warden / Google',
        license='CC BY 4.0', license_url='https://creativecommons.org/licenses/by/4.0/',
        source_md5='854c580ee90bff80c516491c84544e32',
        selection='zero..nine,yes,no; first two filename-sorted globally distinct speaker IDs per label; original PCM; no model-based selection',
        reference_scope='Provided keyword label, not model transcription. Chinese options are declared dictionary equivalents for single keywords, not human bilingual sentence gold. Not CS2 or player IDs; pretraining contamination unknown.',
        speaker_count=len(speakers), cases=cases), ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(dict(cases=len(cases), speakers=len(speakers), seconds=sum(c['duration_seconds'] for c in cases)), ensure_ascii=False))


if __name__ == '__main__':
    main()
