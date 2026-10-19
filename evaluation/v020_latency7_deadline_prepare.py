import hashlib,json
from pathlib import Path
from collections import defaultdict
R=Path(__file__).resolve().parents[1];B=R/'evaluation/results/v020-latency7';O=B/'deadline'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
old=json.loads((B/'manifest.json').read_text())
for p,h in old['files'].items():assert sha(Path(p) if p.startswith('/') else R/p)==h,p
src=defaultdict(list)
for l in (B/'frames.tsv').read_text().splitlines():
 name,t,p=l.split('\t');src[name].append((int(t),p))
rows=[];traces=[]
for name,events in src.items():
 if name.startswith('test'):continue
 for ms in [0,1250,2500,3750]:
  pad=ms*16;end=events[-1][0]+pad
  # All original causal20ms events shifted exactly. Add prefix ticks and hard
  # grid samples with the most recently available value, never a future one.
  shifted={t+pad:p for t,p in events}
  ticks=set(shifted)|set(range(320,pad+1,320))|set(range(80000,end+1,80000))|{end}
  if pad:ticks.add(pad)
  current='0.0';prev=0
  for t in sorted(ticks):
   assert 0<t-prev<=320,(name,ms,t,prev)
   if t in shifted:current=shifted[t]
   rows.append(f'{name}@{ms}\t{t}\t{current}');prev=t
  traces.append(dict(name=f'{name}@{ms}',source=name,padding_ms=ms,padding_samples=pad,samples=end))
tests=[([1.0]*300),([.1]*300),([None]*300),([float('nan')]*300),([0.0]*100+[1.0]*20+[0.0]*40),([1.0]*10+[0.0]*50),([1.0]*10+[0.0]*15+[1.0]*50),([1.0]*219+[0.0]*41),([1.0]*220+[0.0]*40),([0.0]*23+[1.0]*7),([1.0]*250),([1.0]*10+[None]*100+[0.0]*100)]
for i,ps in enumerate(tests):
 for j,p in enumerate(ps):rows.append(f'test{i}\t{(j+1)*320}\t'+('null' if p is None else 'nan' if p!=p else str(p)))
(O/'frames.tsv').write_text('\n'.join(rows)+'\n')
files=dict(old['files'])
for p in ['evaluation/results/v020-latency7/manifest.json','evaluation/results/v020-latency7/frames.tsv','evaluation/results/v020-latency7/product.tsv','evaluation/V020Deadline7.kt','evaluation/v020_latency7_deadline_prepare.py','evaluation/v020_latency7_deadline_audit.py','scripts/run-v020-deadline7-P0','docs/dev/archive/v0.2.0第7轮硬期限时钟对照.md','evaluation/results/v020-latency7/deadline/frames.tsv']:files[p]=sha(R/p)
m=dict(files=files,traces=traces,synthetic_cases=12,policies=['baseline','anchored'],new_model_requests=0,mapping='Shift already-causal20ms events exactly by pad; merge prefix ticks and absolute80000 deadlines; inserted ticks hold latest available probability, no future read. Delta<=320. Both arms same events.',gate='Original P50 -20% and -200ms/P95 nonworse/requests<=+25%/grid coverage no drop; other3 phase P50/P95 no worse. No further variants.')
with (O/'manifest.json').open('x') as f:json.dump(m,f,indent=2)
