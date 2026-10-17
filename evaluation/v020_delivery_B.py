"""Bounded real-clock development replay; one Gemma and async browser telemetry."""
import argparse,base64,contextlib,hashlib,json,queue,subprocess,sys,threading,time,tomllib,wave
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from pathlib import Path
from types import SimpleNamespace
R=Path(__file__).resolve().parents[1];O=R/'evaluation/results/v020-delivery/B'
STATE=R/'evaluation/results/v020-continuation/state.json'
J='/home/hyh/Tools/java/eclipse-temurin-jdk17/bin/java'
NODE='/home/hyh/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node'
MODEL=Path('/home/hyh/Tools/litert/models/gemma-4-E2B-it.litertlm')
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def read(p):return json.loads(Path(p).read_text())
def guard():
 s=read(STATE);a=tomllib.loads(Path('/home/hyh/.codex/automations/opencaption/automation.toml').read_text())
 assert s['status']=='active' and s['phase'].startswith('delivery_B_') and a['status']=='ACTIVE'
 assert s['delivery_scope']['execution_authorized'] and s['delivery_scope']['model_request_cap']==400
 return s
class Protocol:
 def __init__(self):self.p=subprocess.Popen([J,'-Xmx64m','-cp',(O/'classpath.txt').read_text(),'V020DeliveryBProtocol',str(O/'names.txt')],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True)
 def send(self,line):
  self.p.stdin.write(line+'\n');self.p.stdin.flush();s=self.p.stdout.readline()
  if not s:raise RuntimeError('Protocol EOF')
  return s.rstrip('\r\n').split('\t')
 def prompt(self,hints):return [base64.b64decode(x).decode() for x in self.send('prompt\tbilingual\t'+enc(hints))]
 def parse(self,raw,hints):
  f=self.send('parse\tbilingual\t'+enc(hints)+'\t'+enc(raw));r=dict(status=f[0],english='',chinese='',reason='')
  if f[0]=='subtitle':r.update(english=dec(f[1]),chinese=dec(f[2]))
  elif f[0]=='invalid':r['reason']=dec(f[1])
  elif f[0]!='no_speech':raise RuntimeError('Unexpected parser '+str(f))
  return r
 def close(self):
  self.p.stdin.close()
  if self.p.wait(timeout=10)!=0:raise RuntimeError('protocol exit')
def enc(s):return base64.b64encode(s.encode()).decode()
def dec(s):return base64.b64decode(s).decode()
def resources():
 relative=Path('/proc/self/cgroup').read_text().strip().split('::',1)[1];p=Path('/sys/fs/cgroup')/relative.lstrip('/')
 return {k:(p/k).read_text().strip() for k in ['memory.max','memory.current','memory.peak','memory.swap.max','memory.swap.current','memory.events']}
def permit(n):
 q=read(O/'permits'/f'{n}.json')
 assert q['batch']==n and 0<=time.time()-q['at_unix']<180 and q['usage_allowed']
 assert 0<=q['weekly_used']<100 and 0<=q['five_hour_used']<100 # User allows entire remaining week.
 if n:assert (O/'permits'/f'{n-1}-after.json').exists()
 return q
class Web:
 def __init__(self,d):
  self.d=d;self.lock=threading.RLock();self.state={'phase':'idle','batch':-1};self.clients=[];self.hints={'text':'CS2 broadcast.','automatic':True};self.ui_ready=False;self.ui_done=False
  web=self
  class Handler(SimpleHTTPRequestHandler):
   def __init__(self,*a,**kw):super().__init__(*a,directory=str(O/'ui_project/build/web'),**kw)
   def log_message(self,*args):pass
   def reply(self,row,code=200):
    b=json.dumps(row,ensure_ascii=False).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(b)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(b)
   def do_GET(self):
    if self.path=='/clock':return self.reply({'server_ms':time.monotonic_ns()/1e6})
    if self.path=='/status':
     with web.lock:return self.reply(dict(web.state))
    if self.path=='/events':
     q=queue.Queue(maxsize=256)
     with web.lock:web.clients.append(q)
     self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Cache-Control','no-store');self.end_headers()
     try:
      while True:
       try:data='data: '+json.dumps(q.get(timeout=3),ensure_ascii=False)+'\n\n'
       except queue.Empty:data=': keepalive\n\n'
       self.wfile.write(data.encode());self.wfile.flush()
     except (BrokenPipeError,ConnectionResetError):return
     finally:
      with web.lock:
       if q in web.clients:web.clients.remove(q)
    else:return super().do_GET()
   def do_POST(self):
    origin=self.headers.get('Origin')
    if origin and origin!='http://127.0.0.1:8767':return self.reply({'error':'origin'},403)
    n=int(self.headers.get('Content-Length','0'))
    if not 0<n<=65536:return self.reply({'error':'size'},413)
    row=json.loads(self.rfile.read(n));assert isinstance(row,dict)
    with web.lock:
     if self.path=='/telemetry':
      web.log('ui.jsonl',row)
      if row.get('type')=='actual_hints' and row.get('run_id')=='batch-'+str(web.state['batch']):
       h=row['hints'];assert isinstance(h,str) and len(h)<=240;web.hints={'text':h,'automatic':bool(row['automatic'])}
     elif self.path=='/ui_ready':
      assert row['batch']==web.state['batch'];web.ui_ready=True;web.log('transport.jsonl',{'type':'ui_ready',**row})
     elif self.path=='/ui_done':
      assert row['batch']==web.state['batch'];web.ui_done=True;web.log('transport.jsonl',{'type':'ui_done',**row})
     else:return self.reply({'error':'path'},404)
    self.reply({'ok':True})
  self.server=ThreadingHTTPServer(('127.0.0.1',8767),Handler);self.server.daemon_threads=True
  self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
 def log(self,name,row):
  with self.lock:
   with (self.d/name).open('a') as f:f.write(json.dumps(dict(row,server_received_ms=time.monotonic_ns()/1e6),ensure_ascii=False)+'\n')
 def push(self,row):
  with self.lock:
   event=dict(row,server_sent_ms=time.monotonic_ns()/1e6)
   for q in self.clients:
    try:q.put_nowait(event)
    except queue.Full:raise RuntimeError('UI queue overflow, no silent event loss')
   if not self.clients:raise RuntimeError('No UI stream during replay')
 def close(self):
  with self.lock:self.state['phase']='stop'
  self.server.shutdown();self.server.server_close()
def freeze():
 guard();m=read(O/'prepare_manifest.json')
 for p,h in m['files'].items():assert sha(p)==h,p
 b=Protocol()
 try:prompts=b.prompt('CS2 broadcast.');assert b.parse('[NONE]','CS2 broadcast.')['status']=='no_speech'
 finally:b.close()
 paths=[R/'evaluation/v020_delivery_B.py',R/'evaluation/v020_delivery_B_browser.cjs',R/'evaluation/gemma_replay.py',R/'scripts/run-v020-delivery-B',R/'lib/delivery_live_preview.dart',R/'scripts/build-delivery-live-preview',R/'docs/v0.2.0交付包B运行入口冻结_20261016.md',O/'prepare_manifest.json',O/'preparation_audit.json',O/'V020DeliveryBRunnerCapture.java',O/'runner_classpath.txt']+list((O/'runner_classes').rglob('*.class'))
 paths+=list((O/'ui_project/build/web').rglob('*'))
 import litert_lm
 paths+=list(Path(litert_lm.__file__).parent.rglob('*.py'))
 files={str(p):sha(p) for p in paths if p.is_file()}
 frozen={'files':files,'prepare_manifest_sha256':sha(O/'prepare_manifest.json'),'model_sha256':sha(MODEL),'prompts':prompts,'budget':54,'batch_upper_bounds':[r['max_requests'] for r in m['order']],'retries':0,'residencies':1,'context':768,'output':128,'threads':4,'speculative_decoding':None,'inference_ack':'after model completion/parse, never after UI acknowledgement','display':'headful Chromium/Xvfb virtual raster','reference':'ASR-assisted old development proxy, not independent human gold','new_gemma_requests':0}
 with (O/'runner_manifest.json').open('x') as f:json.dump(frozen,f,ensure_ascii=False,indent=2)
 print('RUNNER_FROZEN54 zero Gemma initialization',flush=True)
def run(preflight=False):
 guard();m=read(O/'prepare_manifest.json');frozen=read(O/'runner_manifest.json')
 for p,h in {**m['files'],**frozen['files']}.items():assert sha(p)==h,p
 d=O/('preflight' if preflight else 'live');d.mkdir(exist_ok=True)
 assert not (d/'run.jsonl').exists(),'No implicit retry or duplicate residency'
 limits=resources();assert limits['memory.max']==str((3 if preflight else 6)*1024**3) and limits['memory.swap.max']=='0'
 if not preflight:
  assert read(O/'preflight_audit.json')['passed'] and read(O/'preflight_audit.json')['runner_manifest_sha256']==sha(O/'runner_manifest.json')
  assert guard()['delivery_scope']['actual_requests']+54<=400
  permit(0);assert sha(MODEL)==frozen['model_sha256']
 web=Web(d);node=None;model=None;cap=None;proto=Protocol();total=0
 def log(row):web.log('run.jsonl',row)
 def wait_until(test,seconds,what):
  end=time.monotonic()+seconds
  while not test():
   guard()
   if node is not None and node.poll() is not None:raise RuntimeError('Browser agent exited: '+str(node.returncode))
   if time.monotonic()>end:raise TimeoutError(what)
   time.sleep(.1)
 try:
  log({'type':'metadata','preflight_stub':preflight,'resources':limits,'runner_sha256':sha(O/'runner_manifest.json')})
  node=subprocess.Popen(['xvfb-run','-a','-s','-screen 0 1280x900x24',NODE,str(R/'evaluation/v020_delivery_B_browser.cjs'),str(d)],stdout=(d/'browser.log').open('w'),stderr=subprocess.STDOUT)
  if not preflight:
   from gemma_replay import LiteRtRuntime
   begin=time.monotonic()
   with contextlib.redirect_stdout(sys.stderr):model=LiteRtRuntime(SimpleNamespace(model=MODEL,threads=4,max_new_tokens=128,hints='',task='bilingual',task_profile='baseline',system_profile='minimal',cache_mode='disk',speculative_decoding='default',max_context_tokens=768))
   log({'type':'loaded','load_ms':(time.monotonic()-begin)*1000,'resources':resources()});print('MODEL_READY',flush=True)
  for item in m['order'][:1] if preflight else m['order']:
   batch=item['batch']
   if not preflight:
    command=O/'commands'/str(batch);wait_until(command.exists,240,'batch command')
    assert command.read_text().strip()==f'batch {batch}';permit(batch)
   with web.lock:web.state={'phase':'prepare','batch':batch};web.ui_ready=web.ui_done=False;web.hints={'text':'CS2 broadcast.','automatic':True}
   wait_until(lambda:web.ui_ready,60,'browser UI ready')
   if not preflight:permit(batch)
   piece=m['pieces'][item['piece']];wav=O/f'input-{batch}.wav';q=queue.Queue(maxsize=2);command_lock=threading.Lock();capture_done=threading.Event();armed=threading.Event();calibration={}
   cap=subprocess.Popen([J,'-Xmx192m','-cp',(O/'runner_classpath.txt').read_text(),'V020DeliveryBRunnerCapture',str(R),str(R/piece['path']),str(wav),'30',item['strategy'],'live'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=(d/f'capture-{batch}.log').open('w'),text=True)
   def command(line):
    with command_lock:cap.stdin.write(line+'\n');cap.stdin.flush()
   def reader():
    try:
     for line in cap.stdout:
      v=line.rstrip('\r\n').split('\t');kind=v[0]
      if kind=='ARMED':armed.set();log({'type':'capture_armed','batch':batch})
      elif kind=='CLOCK':log({'type':'clock_calibration','batch':batch,'java_clock_ms':int(v[1]),'python_begin_before_ms':calibration['before'],'python_clock_received_ms':time.monotonic_ns()/1e6})
      elif kind=='REQ':q.put(v,timeout=10)
      elif kind=='END':log({'type':'capture_end','batch':batch,'fields':v[1:]});q.put(None);return
      elif kind=='ERR':raise RuntimeError(dec(v[1]))
      else:
       log({'type':'capture_event','batch':batch,'kind':kind,'fields':v[1:],'resources':resources() if kind=='ACT' else None})
       if kind=='ACT':web.push({'type':'activity','id':f'b{batch}a{v[1]}','audio_ms':int(v[1])})
       elif kind=='GAP':web.push({'type':'gap','id':f'b{batch}gap{v[1]}','start_ms':int(v[2]),'end_ms':int(v[3])})
     raise RuntimeError('capture EOF without END')
    except BaseException as e:q.put(e)
   def hints():
    sent=None
    try:
     while not capture_done.wait(.02):
      with web.lock:h=dict(web.hints)
      if h!=sent:command('HINT\t'+enc(h['text'])+'\t'+str(h['automatic']).lower());sent=h;log({'type':'hints_forwarded','batch':batch,**h})
    except (BrokenPipeError,ValueError):pass
   thread=threading.Thread(target=reader,daemon=True);thread.start()
   wait_until(armed.is_set,30,'capture ARMED before BEGIN')
   before=time.monotonic_ns()/1e6;calibration['before']=before;command('BEGIN');log({'type':'begin_sent','batch':batch,'python_before_ms':before,'python_after_ms':time.monotonic_ns()/1e6})
   hint_thread=threading.Thread(target=hints,daemon=True);hint_thread.start();count=0
   try:
    while True:
     v=q.get(timeout=150)
     if v is None:break
     if isinstance(v,BaseException):raise v
     guard();assert count<item['max_requests'] and total<54
     event_id=f'b{batch}w{v[1]}';h=dec(v[8]);system,prompt=proto.prompt(h);input_sha=sha(wav)
     log({'type':'started_stub' if preflight else 'started','batch':batch,'piece':item['piece'],'strategy':item['strategy'],'event_id':event_id,'window':int(v[1]),'start_ms':int(v[2]),'end_ms':int(v[3]),'java_started_ms':int(v[4]),'submitted_ms':int(v[5]),'source_samples':int(v[6]),'input_samples':int(v[7]),'input_sha256':input_sha,'hints':h,'verification':v[9]=='true'})
     began=time.monotonic()
     if preflight:raw='English: Local transport check.\nChinese: 本机传输检查。'
     else:
      model.system_message=system;model.prompt=prompt
      with contextlib.redirect_stdout(sys.stderr):raw=model.infer(wav)
     parsed=proto.parse(raw,h);done=time.monotonic_ns()/1e6
     row={'type':'stub_result' if preflight else 'result','batch':batch,'piece':item['piece'],'strategy':item['strategy'],'event_id':event_id,'window':int(v[1]),'start_ms':int(v[2]),'end_ms':int(v[3]),'absolute_start_ms':piece['absolute_start_ms']+int(v[2]),'absolute_end_ms':piece['absolute_start_ms']+int(v[3]),'model_finished_server_ms':done,'inference_ms':(time.monotonic()-began)*1000,'input_sha256':input_sha,'hints':h,'raw':raw,**parsed}
     log(row);command('ACK');log({'type':'model_ack_sent','batch':batch,'event_id':event_id})
     if parsed['status']=='subtitle':web.push({'type':'subtitle','id':event_id,'window':int(v[1]),'start_ms':int(v[2]),'end_ms':int(v[3]),'english':parsed['english'],'chinese':parsed['chinese'],'hints':h})
     elif parsed['status']=='invalid':web.push({'type':'gap','id':event_id,'start_ms':int(v[2]),'end_ms':int(v[3])})
     else:web.push({'type':'no_speech','id':event_id})
     count+=1;total+=1
    assert cap.wait(timeout=10)==0
   finally:
    capture_done.set();hint_thread.join(timeout=2)
    if cap.poll() is None:cap.kill()
    cap.wait(timeout=10);cap.stdin.close();thread.join(timeout=2)
   with web.lock:web.state['phase']='drain'
   wait_until(lambda:web.ui_done,20,'UI drain between independent runs')
   log({'type':'batch_complete','batch':batch,'requests':count,'total':total,'stub':preflight,'resources':resources()});print(f'BATCH_COMPLETE {batch} requests={count} total={total}',flush=True)
  log({'type':'complete','requests':0 if preflight else total,'stub_requests':total if preflight else 0,'resources':resources()});print('COMPLETE '+str(total),flush=True)
 except BaseException as e:log({'type':'failure','error':repr(e),'requests_so_far':total,'preflight_stub':preflight});raise
 finally:
  with web.lock:web.state['phase']='stop'
  if cap is not None and cap.poll() is None:cap.kill();cap.wait(timeout=10)
  try:
   if model is not None:model.close()
  finally:
   try:proto.close()
   except Exception as error:log({'type':'cleanup_protocol_error','error':str(error)})
  if node is not None:
   try:node.wait(timeout=15)
   except subprocess.TimeoutExpired:node.terminate();node.wait(timeout=10)
  web.close()
if __name__=='__main__':
 {'freeze':freeze,'preflight':lambda:run(True),'serve':lambda:run(False)}[sys.argv[1]]()
