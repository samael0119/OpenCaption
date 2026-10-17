"""Supported original OPUS-MT -> CTranslate2 conversion, zero inference."""
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evaluation/results/v020-mt6'
os.environ['OMP_NUM_THREADS']='4'
sys.path.insert(0,str(ROOT/'evaluation/results/s0-20261013/deps'))
sys.path.insert(0,str(OUT/'deps'))


def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for c in iter(lambda:f.read(1048576),b''):h.update(c)
    return h.hexdigest()


def main():
    import ctranslate2,sentencepiece,numpy,yaml
    assert ctranslate2.__version__=='4.6.0' and sentencepiece.__version__=='0.2.1'
    assert numpy.__version__=='2.2.6' and yaml.__version__=='6.0.2'
    original=OUT/'original';vocab=yaml.safe_load((original/'opus.spm32k-spm32k.vocab.yml').read_text())
    assert vocab['>>cmn_Hans<<']==5 and vocab['</s>']==0
    if (OUT/'ct2-int8').exists():raise RuntimeError('Conversion already started; never force overwrite')
    t=time.monotonic()
    converter=ctranslate2.converters.OpusMTConverter(str(original))
    converter.convert(str(OUT/'ct2-int8'),quantization='int8',force=False)
    files={}
    for folder in [OUT/'ct2-int8',OUT/'deps']:
        for p in folder.rglob('*'):
            if p.is_file() and p.suffix!='.pyc':files[str(p.relative_to(ROOT))]=digest(p)
    result=dict(complete=True,inference_requests=0,conversion_ms=(time.monotonic()-t)*1000,
        ctranslate2=ctranslate2.__version__,sentencepiece=sentencepiece.__version__,numpy=numpy.__version__,pyyaml=yaml.__version__,
        compute_types=sorted(ctranslate2.get_supported_compute_types('cpu')),target_language_prefix='>>cmn_Hans<<',prefix_vocab_id=5,
        source_license='Original archive LICENSE is CC-BY-4.0; HF model card Apache-2.0 differs. Preserve both provenance records; no redistribution in this experiment.',
        files=files)
    (OUT/'conversion.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='files'},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
