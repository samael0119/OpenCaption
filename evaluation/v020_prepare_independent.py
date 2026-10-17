"""Freeze bounded public fixtures before looking at any model output.

English supplied references only; these are not Chinese gold or independent
CS2 matches. Weak/mixed variants are synthetic transforms, explicitly labeled.
"""
import array
import hashlib
import json
import math
from pathlib import Path
import subprocess
import wave

import pyarrow
import pyarrow.parquet as pq

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evaluation/results/v020-independent'
ASSETS=OUT/'assets'
RATE=16000


def decode(source,target,start=None,duration=None):
    cmd=['ffmpeg','-nostdin','-v','error','-threads','1']
    if start is not None: cmd+=['-ss',str(start)]
    cmd+=['-i',str(source)]
    if duration is not None: cmd+=['-t',str(duration)]
    cmd+=['-ar',str(RATE),'-ac','1','-c:a','pcm_s16le','-y',str(target)]
    subprocess.run(cmd,check=True,timeout=60)


def read(path):
    with wave.open(str(path)) as w:
        assert (w.getnchannels(),w.getsampwidth(),w.getframerate())==(1,2,RATE)
        values=array.array('h',w.readframes(w.getnframes()))
    return values


def save(path,values):
    with wave.open(str(path),'wb') as w:
        w.setparams((1,2,RATE,len(values),'NONE','not compressed'))
        w.writeframes(values.tobytes())


def describe(path):
    values=read(path)
    return {'path':str(path.relative_to(ROOT)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'samples':len(values),'seconds':len(values)/RATE,'nonzero':sum(v!=0 for v in values),
            'rms_pcm16':math.sqrt(sum(v*v for v in values)/max(1,len(values)))}


def main():
    manifest=OUT/'frozen_cases.json'
    if manifest.exists():
        raise RuntimeError('Frozen cases already exist; review before altering the held-out pack')
    cases=[]
    rows=pq.read_table(ASSETS/'librispeech_dummy.parquet').to_pylist()
    folder=OUT/'speech';folder.mkdir(exist_ok=True)
    for row in sorted(rows,key=lambda x:x['id']):
        identifier=row['id']
        if not identifier or any(c not in '0123456789-' for c in identifier):raise ValueError('invalid source id')
        flac=folder/f'{identifier}.flac'; wav=folder/f'{identifier}.wav'
        flac.write_bytes(row['audio']['bytes']);decode(flac,wav)
        info=describe(wav)
        if 1<=info['seconds']<=5:
            cases.append({'id':identifier,'kind':'published_read_speech','reference_en':row['text'],
                'reference_zh':None,'speaker_id':row['speaker_id'],**info})
        if len(cases)==12:break
    if len(cases)<12:raise ValueError('insufficient <=5s utterances')
    original=list(cases)
    music=OUT/'music';music.mkdir(exist_ok=True)
    for start in [10,30,60,120]:
        wav=music/f'piano_{start}.wav';decode(ASSETS/'chopin_cc0.ogg',wav,start,5)
        info=describe(wav); assert info['nonzero']>0
        cases.append({'id':f'piano-{start}','kind':'instrumental_music','reference_en':'',
            'reference_zh':'','expect_no_speech':True,'source_start_seconds':start,**info})
    piano=read(music/'piano_30.wav')
    piano_rms=math.sqrt(sum(v*v for v in piano)/len(piano))
    for item in original[:4]:
        values=read(ROOT/item['path'])
        for db in [-18,-30]:
            variant=folder/f"{item['id']}_atten{db}.wav"
            save(variant,array.array('h',(round(v*10**(db/20)) for v in values)))
            cases.append({'id':f"{item['id']}-atten{db}",'kind':'synthetic_attenuation_not_real_weak_recording',
                'reference_en':item['reference_en'],'reference_zh':None,'parent_id':item['id'],
                'gain_db':db,**describe(variant)})
        rms=math.sqrt(sum(v*v for v in values)/len(values))
        gain=rms/(piano_rms*10**(10/20))
        mixed=array.array('h',(max(-32768,min(32767,round(v+piano[i%len(piano)]*gain))) for i,v in enumerate(values)))
        variant=folder/f"{item['id']}_music10db.wav";save(variant,mixed)
        cases.append({'id':f"{item['id']}-music10db",'kind':'synthetic_mix_of_real_speech_and_real_music',
            'reference_en':item['reference_en'],'reference_zh':None,'parent_id':item['id'],
            'nominal_snr_db':10,**describe(variant)})
    result={'frozen_before_inference':True,'selection':'Sorted source IDs, first 12 utterances with full duration 1..5 seconds; first 4 selected for transforms; music starts 10/30/60/120 sec',
        'source_rows':len(rows),'selected_original':len(original),'selected_speaker_ids':sorted({i['speaker_id'] for i in original}),
        'cases':cases,'pyarrow_version':pyarrow.__version__,
        'reference_policy':'Published supplied English reference, never Gemma output. No independent Chinese gold; no CS2 quality claim. Transforms are not additional independent sessions.',
        'evaluation_scope':'Protocol, whole-utterance English WER, no-speech music, weak/mixed regression, cost. Four configurations kept distinct; only score supported metrics.',
        'sources':json.loads((OUT/'source_inventory.json').read_text())}
    manifest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['source_rows','selected_original','selected_speaker_ids','pyarrow_version']},indent=2))
    print('frozen cases',len(cases),'natural seconds',sum(i['seconds'] for i in original))


if __name__=='__main__':main()
