"""Compare isolated before/after actual Kotlin parsers on frozen old raw outputs.

No audio inference or old-manifest modification. Historical name context is not
reconstructed: both bridges use the same default preserved-name set.
"""
import base64
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evaluation/results/v020-round2/protocol'
JAVA='/home/hyh/Tools/java/eclipse-temurin-jdk17/bin/java'
SOURCES=[
 'evaluation/results/v020-convergence/g1_requests.jsonl',
 'evaluation/results/v020-convergence/coupling1_requests.jsonl',
 'evaluation/results/v020-convergence/gain1_requests.jsonl',
 'evaluation/results/v020-convergence/gain2_requests.jsonl',
 'evaluation/results/v020-independent/joint_live_run1_model.jsonl',
]


def digest(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()


class Bridge:
    def __init__(self,phase):
        cp=str(OUT/(phase+'-bridge'))+':'+(OUT/(phase+'-classpath.txt')).read_text().strip()
        self.process=subprocess.Popen([JAVA,'-Xmx64m','-cp',cp,'V020ProtocolBridge'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)

    def parse(self,task,raw):
        code=base64.b64encode(raw.encode()).decode()
        self.process.stdin.write('parse\t'+task+'\t'+code+'\n');self.process.stdin.flush()
        # English-only tasks end with an empty Chinese field; retain its tab.
        fields=self.process.stdout.readline().rstrip('\r\n').split('\t')
        if not fields or fields[0] not in ['subtitle','invalid','no_speech']:raise RuntimeError('Bridge failed')
        result=dict(status=fields[0],english='',chinese='',reason='')
        if fields[0]=='subtitle':
            result['english']=base64.b64decode(fields[1]).decode();result['chinese']=base64.b64decode(fields[2]).decode()
        elif fields[0]=='invalid':result['reason']=base64.b64decode(fields[1]).decode()
        return result

    def close(self):
        self.process.stdin.close();self.process.wait(timeout=10)


def main():
    if (OUT/'replay_rows.jsonl').exists():raise RuntimeError('Replay already exists; inspect, not overwrite')
    frozen=dict(at=datetime.now().astimezone().isoformat(),source_files={p:digest(ROOT/p) for p in SOURCES},
        product_source_files={p:digest(ROOT/p) for p in [
            'android/app/src/main/kotlin/dev/opencaption/opencaption/E2eProtocol.kt',
            'android/app/src/test/kotlin/dev/opencaption/opencaption/E2eProtocolTest.kt',
            'evaluation/v020_round2_protocol_replay.py']},
        class_files={phase:{str(p.relative_to(OUT)):digest(p) for p in Path((OUT/(phase+'-classpath.txt')).read_text().strip().split(':')[0]).rglob('*.class')} for phase in ['before','after']},
        scope='Raw-output parser replay, same default name context. No new model/audio calls, independent semantic gain, silence truth labels or UI timing.')
    (OUT/'replay_manifest.json').write_text(json.dumps(frozen,ensure_ascii=False,indent=2)+'\n')
    before=Bridge('before');after=Bridge('after');counts=Counter();changes=[];losses=[];by_source={}
    try:
        with (OUT/'replay_rows.jsonl').open('x') as output:
            for path in SOURCES:
                group=Counter()
                for line in (ROOT/path).read_text().splitlines():
                    row=json.loads(line)
                    eligible=row.get('type')=='result' if path.endswith('joint_live_run1_model.jsonl') else row.get('type')=='request' and 'task' in row
                    if not eligible:continue
                    raw=row['raw'];task=row.get('task','bilingual')
                    a,b=before.parse(task,raw),after.parse(task,raw)
                    result=dict(source=path,index=row.get('index'),case_id=row.get('case_id'),window=row.get('window'),task=task,
                                raw_sha256=hashlib.sha256(raw.encode()).hexdigest(),before=a,after=b)
                    counts['cases']+=1;group['cases']+=1
                    counts['before_'+a['status']]+=1;counts['after_'+b['status']]+=1
                    if a!=b:
                        counts['any_change']+=1
                        if a['status']!=b['status']:counts['status_change']+=1
                        result['raw']=raw;changes.append(result)
                    if a['status']=='subtitle' and (b['status']!='subtitle' or a['english']!=b['english'] or a['chinese']!=b['chinese']):losses.append(result)
                    output.write(json.dumps(result,ensure_ascii=False)+'\n')
                by_source[path]=dict(group)
    finally:
        before.close();after.close()
    summary=dict(complete=True,counts=dict(counts),by_source=by_source,changes=changes,
        delivered_subtitle_changes=losses,protocol_only_improvement=True,
        source_audio_recognition_improved=False,new_model_requests=0,independent_acceptance_passed=False,
        note='invalid toNoSpeech normalizes model abstention; original voiced reference may still be missed. No content or hallucination repair claim.')
    (OUT/'replay_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    if losses:raise RuntimeError('Delivered subtitles changed; review regression')


if __name__=='__main__':main()
