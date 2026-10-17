"""Freeze natural whispered foreground speech, not amplified/attenuated audio."""
from array import array
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import subprocess
import wave

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'evaluation/results/v020-independent'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    target = OUT/'whisper_holdout_cases.json'
    if target.exists():
        raise RuntimeError('Holdout already frozen; no output-based reselection')
    original = OUT/'assets/nam_original'
    converted = OUT/'whisper_holdout'
    converted.mkdir(exist_ok=True)
    cases = []
    for source in sorted((original/'VOICECOMMAND-NOISY').glob('*_headset.wav')):
        identifier = source.name.split('_')[0]
        reference_file = original/'VOICECOMMAND-TEXT'/(identifier+'.txt')
        reference = reference_file.read_text().strip()
        with wave.open(str(source)) as wav:
            assert wav.getnchannels()==1 and wav.getsampwidth()==2 and wav.getframerate()==96000
            source_samples = wav.getnframes()
            assert source_samples/96000 <= 5
        output = converted/(f'whisper-{identifier}.wav')
        subprocess.run(['ffmpeg','-nostdin','-v','error','-threads','1','-i',str(source),
                        '-map','0:a:0','-ac','1','-ar','16000','-c:a','pcm_s16le','-n',str(output)],check=True)
        with wave.open(str(output)) as wav:
            samples=wav.getnframes(); pcm=array('h',wav.readframes(samples))
        assert 0<samples<=80000
        cases.append(dict(id=f'whisper-{identifier}',kind='recorded_whisper_with_played_cafeteria_noise',
            path=str(output.relative_to(ROOT)),reference_en=reference,
            source_path=str(source.relative_to(ROOT)),source_sha256=sha(source),
            reference_path=str(reference_file.relative_to(ROOT)),reference_sha256=sha(reference_file),
            sha256=sha(output),source_sample_rate=96000,source_samples=source_samples,
            samples=samples,duration_seconds=samples/16000,
            rms=math.sqrt(sum(x*x for x in pcm)/samples)/32768,peak=max(abs(x) for x in pcm)/32768))
    assert len(cases)==18
    manifest=dict(frozen_utc=datetime.now(timezone.utc).isoformat(),
        attribution='Yamagishi, Brown, Yang, Clark, King (2021), CSTR NAM TIMIT Plus, University of Edinburgh / CSTR, DOI 10.7488/ds/2994',
        source_url='https://datashare.ed.ac.uk/items/30d10e2e-0ccb-483b-b499-8b3c98ad0a2c',
        source_license='ODC-By 1.0, as stated in publisher README/COPYING; local evaluation, no audio redistribution',
        archive_expected_md5='d82a9594a4eaed8c06c5527367e31453',
        archive_full_hash_verified=False, archive_read_bytes=12582912,
        prefix_sha256=sha(OUT/'assets/nam_archive_prefix12m.bz2'),
        transport='HTTPS Range 0..12582911 with matching publisher ETag; full archive was not downloaded',
        selection='All 18 VOICECOMMAND headset recordings, file-name order; paired published prompt text; before any model/VAD output',
        conversion='Original mono16-bit PCM96kHz -> mono16-bit PCM16kHz; no trim, volume gain, normalization or added noise',
        speaker_count=1, reference_scope='Published intended command text, not model transcript or independently re-transcribed bilingual gold. Real human whisper with physically played cafeteria noise; not a live CS2 match, no Chinese gold; pretraining contamination unknown.',
        cases=cases)
    target.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    (OUT/'whisper_vad_cases.tsv').write_text(''.join(f"{c['id']}\tspeech\t{c['path']}\n" for c in cases))
    prior=json.loads((OUT/'speech_evidence_plan.json').read_text())
    (OUT/'whisper_vad_plan.json').write_text(json.dumps(dict(
        cases=[dict(id=c['id'],label='speech') for c in cases],rule=prior['rule'],
        scope='Independent natural-whisper diagnostic holdout, one headset speaker; same frozen rule, no tuning or product veto enabled'),
        ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(dict(cases=18,speakers=1,seconds=sum(c['duration_seconds'] for c in cases),
                         rms_min=min(c['rms'] for c in cases),rms_max=max(c['rms'] for c in cases)),ensure_ascii=False))


if __name__=='__main__':
    main()
