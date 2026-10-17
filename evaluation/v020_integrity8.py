"""Freeze, compile and audit old raw output. Zero model/audio calls."""
import base64, collections, datetime, hashlib, json, pathlib, subprocess, sys
R=pathlib.Path(__file__).resolve().parents[1];O=R/'evaluation/results/v020-integrity8'
J='/home/hyh/Tools/java/eclipse-temurin-jdk17/bin/java'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(name,data):
    with (O/name).open('x') as f:json.dump(data,f,ensure_ascii=False,indent=2)
def jar(g,n,v):return next((R/'.gradle/caches/modules-2/files-2.1'/g/n/v).rglob('*.jar'))
def freeze():
    old=json.loads((R/'evaluation/results/v020-round2/protocol/replay_manifest.json').read_text())
    for p,h in old['source_files'].items():assert sha(R/p)==h,p
    cp=[jar('org.jetbrains.kotlin',n,'2.2.21') for n in ['kotlin-compiler-embeddable','kotlin-stdlib','kotlin-script-runtime','kotlin-reflect']]
    cp += [jar('org.jetbrains.kotlinx','kotlinx-coroutines-core-jvm','1.9.0'),jar('org.jetbrains','annotations','23.0.0')]
    paths=list(old['source_files'])+['evaluation/results/v020-round2/protocol/replay_manifest.json','evaluation/results/v020-round2/protocol/replay_rows.jsonl','evaluation/V020Integrity8.kt','evaluation/v020_integrity8.py','scripts/run-v020-integrity8-P0','docs/v0.2.0第8轮输出完整性计划.md','android/app/src/main/kotlin/dev/opencaption/opencaption/E2eProtocol.kt','android/app/src/main/kotlin/dev/opencaption/opencaption/E2ePreservedNames.kt']
    write('manifest.json',dict(at=datetime.datetime.now().astimezone().isoformat(),files={p:sha(R/p) for p in paths},sources=list(old['source_files']),compiler_files={str(p):sha(p) for p in cp},new_model_requests=0,expected_rows=1156,rules='All applicable frozen rows. Multiple distinct pairs are ambiguous, not proven lost speech. Prefix/suffix and repeated labels recorded as structural anomalies. Exact duplicated pairs separate. No new semantic ratings or independent truth. Empty name set matches old bridge.'))
def verify():
    m=json.loads((O/'manifest.json').read_text())
    for p,h in m['files'].items():assert sha(R/p)==h,p
    for p,h in m['compiler_files'].items():assert sha(pathlib.Path(p))==h,p
    return m
def compile_current():
    m=verify();cp=list(m['compiler_files']);classes=O/'classes';classes.mkdir()
    sources=['android/app/src/main/kotlin/dev/opencaption/opencaption/E2eProtocol.kt','android/app/src/main/kotlin/dev/opencaption/opencaption/E2ePreservedNames.kt','evaluation/V020Integrity8.kt']
    cmd=[J,'-Xmx256m','-cp',':'.join(cp),'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler','-no-stdlib','-no-reflect','-jvm-target','17','-classpath',':'.join(cp[1:]),'-d',str(classes)]+[str(R/p) for p in sources]
    subprocess.run(cmd,check=True)
    write('compile.json',dict(command=cmd,class_files={str(p.relative_to(O)):sha(p) for p in classes.rglob('*.class')},runtime_classpath=str(classes)+':'+cp[1]))
class Bridge:
    def __init__(self):
        c=json.loads((O/'compile.json').read_text())
        for p,h in c['class_files'].items():assert sha(O/p)==h
        self.p=subprocess.Popen([J,'-Xmx96m','-cp',c['runtime_classpath'],'V020Integrity8'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
    def call(self,task,raw):
        self.p.stdin.write(task+'\t'+base64.b64encode(raw.encode()).decode()+'\n');self.p.stdin.flush()
        f=self.p.stdout.readline().rstrip('\r\n').split('\t');assert len(f)==5,f
        dec=lambda v:base64.b64decode(v).decode()
        result=dict(status=f[0],english='',chinese='',reason='')
        if f[0]=='subtitle':result.update(english=dec(f[1]),chinese=dec(f[2]))
        if f[0]=='invalid':result['reason']=dec(f[1])
        pairs=[]
        for v in f[4].split(';') if f[4] else []:
            a,b,en,zh=v.split(',');pairs.append(dict(start=int(a),end=int(b),english=dec(en),chinese=dec(zh)))
        return result,dec(f[3]),pairs
    def close(self):self.p.stdin.close();assert self.p.wait(timeout=10)==0

def audit():
    m=verify();b=Bridge();rows=[];old=[json.loads(l) for l in (R/'evaluation/results/v020-round2/protocol/replay_rows.jsonl').read_text().splitlines()];counts=collections.Counter();by_source={};raws=set();anomalies=[]
    try:
        for src in m['sources']:
            group=collections.Counter()
            for line_no,l in enumerate((R/src).read_text().splitlines(),1):
                r=json.loads(l);eligible=r.get('type')=='result' if src.endswith('joint_live_run1_model.jsonl') else r.get('type')=='request' and 'task' in r
                if not eligible:continue
                raw=r['raw'];task=r.get('task','bilingual');result,cleaned,pairs=b.call(task,raw)
                prev=old[len(rows)];h=hashlib.sha256(raw.encode()).hexdigest()
                assert (prev['source'],prev['raw_sha256'],prev['task'])==(src,h,task)
                assert result==prev['after'],(src,line_no,result,prev['after'])
                categories=[];prefix=cleaned[:pairs[0]['start']] if pairs else '';suffix=cleaned[pairs[-1]['end']:] if pairs else ''
                if len(pairs)>1:
                    unique={(p['english'].strip(),p['chinese'].strip()) for p in pairs}
                    categories.append('exact_duplicate_pairs' if len(unique)==1 else 'multiple_distinct_pairs_ambiguous')
                if prefix.strip():categories.append('unmatched_prefix')
                if suffix.strip():categories.append('unmatched_suffix')
                if result['status']=='subtitle' and '[NONE]' in cleaned.upper():categories.append('sentinel_in_accepted_raw')
                # Unknown label inside a matched field is evidence for inspection,
                # not an automatic truth or correction judgment.
                import re
                if result['status']=='subtitle' and re.search(r'(?im)^\s*(?:Explanation|Correction|Note|Analysis|Reasoning|French|German|Spanish|Original)\s*:',cleaned):categories.append('extra_label_in_accepted_raw')
                counts['rows']+=1;counts['status_'+result['status']]+=1;counts['task_'+task]+=1;group['rows']+=1
                for c in categories:counts[c]+=1
                raws.add(h)
                row=dict(source=src,line_no=line_no,index=r.get('index'),case_id=r.get('case_id'),window=r.get('window'),task=task,raw_sha256=h,current=result,raw=raw,cleaned=cleaned,pairs=pairs,pair_count=len(pairs),ignored_prefix=prefix,ignored_suffix=suffix,categories=categories)
                rows.append(row)
                if categories:anomalies.append(row)
            by_source[src]=dict(group)
        assert len(rows)==1156
        probes=[('single','English: Go.\nChinese: 去。'),('different','English: Go.\nChinese: 去。\nEnglish: Stop.\nChinese: 停。'),('duplicate','English: Go.\nChinese: 去。\nEnglish: Go.\nChinese: 去。'),('correction','English: Go.\nChinese: 去。\nCorrection: Previous was wrong.\nEnglish: Stop.\nChinese: 停。'),('prefix','Explanation: test\nEnglish: Go.\nChinese: 去。'),('suffix','English: Go.\nChinese: 去。\nNote: extra'),('none_mix','[NONE]\nEnglish: Go.\nChinese: 去。'),('missing','English: Go.'),('unknown','French: Go.\nChinese: 去。'),('numeric','English: 2\nChinese: 2'),('truncated','English: Go.\nChinese:'),('pure_none','[NONE]\nEnglish: [NONE]\nChinese: [NONE]')]
        probe_rows=[]
        for name,raw in probes:
            result,cleaned,pairs=b.call('bilingual',raw);probe_rows.append(dict(name=name,raw=raw,result=result,cleaned=cleaned,pairs=pairs))
    finally:b.close()
    for name,data in [('rows.jsonl',rows),('anomalies.jsonl',anomalies),('mechanism_probes.jsonl',probe_rows)]:
        with (O/name).open('x') as f:
            for row in data:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    summary=dict(complete=True,counts=dict(counts),by_source=by_source,unique_raw=len(raws),anomalous_rows=len(anomalies),unique_anomalous_raw=len({r['raw_sha256'] for r in anomalies}),same_as_old_current_replay=len(rows),new_model_requests=0,mechanism_probes=len(probe_rows),semantic_truth_reassessed=False,independent_acceptance=False)
    write('summary.json',summary);print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':{'freeze':freeze,'compile':compile_current,'audit':audit}[sys.argv[1]]()
