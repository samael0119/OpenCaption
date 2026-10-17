"""Standalone single-thread VAD cost; no Gemma resident or concurrency claim."""
import hashlib
import json
import resource
import statistics
import time

from s0_probe import OUT as S0, pcm_file, write_json, percentile


def main():
    import numpy as np
    import onnxruntime as ort
    model=S0/'assets/silero_vad.onnx'
    options=ort.SessionOptions()
    options.intra_op_num_threads=options.inter_op_num_threads=1
    began=time.monotonic()
    vad=ort.InferenceSession(str(model),options,providers=['CPUExecutionProvider'])
    init_ms=(time.monotonic()-began)*1000
    pcm=pcm_file(S0/'clip.wav')
    audio=np.frombuffer(pcm,dtype='<i2').astype(np.float32)/32768
    cached=json.loads((S0/'clip_vad.json').read_text())
    runs=[]
    for repeat in range(3):
        state=np.zeros((2,1,128),dtype=np.float32)
        context=np.zeros((1,64),dtype=np.float32)
        probabilities=[];costs=[]
        began=time.monotonic()
        for offset in range(0,len(audio),512):
            frame=audio[offset:offset+512]
            if len(frame)<512:frame=np.pad(frame,(0,512-len(frame)))
            combined=np.concatenate([context,frame.reshape(1,512)],axis=1)
            call=time.monotonic()
            probability,state=vad.run(None,{'input':combined,'state':state,'sr':np.array(16000,dtype=np.int64)})
            costs.append((time.monotonic()-call)*1000)
            context=combined[:,-64:]
            probabilities.append(float(probability[0,0]))
        elapsed=time.monotonic()-began
        assert len(probabilities)==len(cached)
        delta=max(abs(a-b) for a,b in zip(probabilities,cached))
        assert delta<1e-6
        runs.append(dict(repeat=repeat+1,elapsed_ms=elapsed*1000,rtf=elapsed/(len(audio)/16000),
            frames=len(costs),p50_frame_ms=statistics.median(costs),p95_frame_ms=percentile(costs,.95),
            max_frame_ms=max(costs),probability_max_delta=delta))
    result=dict(model_sha256=hashlib.sha256(model.read_bytes()).hexdigest(),init_ms=init_ms,
        threads=1,onnxruntime=ort.__version__,peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        scope='Standalone VAD only; no Gemma resource contention or live capture',runs=runs)
    write_json(S0/'local_followup/vad_cost.json',result)
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
