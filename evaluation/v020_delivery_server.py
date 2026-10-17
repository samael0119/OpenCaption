"""Loopback-only cache/telemetry server. No audio, model, or inference ACK."""
import argparse,json,time,threading,queue
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'evaluation/results/v020-delivery/A'
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--port',type=int,default=8766);ap.add_argument('--web',type=Path,required=True);a=ap.parse_args()
 OUT.mkdir(parents=True,exist_ok=True);commands=queue.Queue(maxsize=128)
 log_lock=threading.Lock();telemetry=OUT/'visible_telemetry.jsonl'
 def record(row):
  row['server_received_ms']=time.monotonic_ns()/1e6
  with log_lock:
   with telemetry.open('a') as f:f.write(json.dumps(row,ensure_ascii=False)+'\n')
 class Handler(SimpleHTTPRequestHandler):
  def __init__(self,*args,**kwargs):super().__init__(*args,directory=str(a.web),**kwargs)
  def log_message(self,*args):pass
  def reply(self,value,code=200):
   b=json.dumps(value,ensure_ascii=False).encode();self.send_response(code);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
  def do_GET(self):
   if self.path=='/clock':return self.reply({'server_ms':time.monotonic_ns()/1e6})
   if self.path=='/events':
    self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Cache-Control','no-store');self.end_headers()
    try:
     while True:
      try:event=commands.get(timeout=10);data='data: '+json.dumps(event,ensure_ascii=False)+'\n\n'
      except queue.Empty:data=': heartbeat\n\n'
      self.wfile.write(data.encode());self.wfile.flush()
    except (BrokenPipeError,ConnectionResetError):return
   else:return super().do_GET()
  def do_POST(self):
   origin=self.headers.get('Origin')
   if origin and origin not in (f'http://127.0.0.1:{a.port}',f'http://localhost:{a.port}'):return self.reply({'error':'origin'},403)
   n=int(self.headers.get('Content-Length','0'))
   if not 0<n<=65536:return self.reply({'error':'size'},413)
   try:row=json.loads(self.rfile.read(n))
   except (ValueError,UnicodeDecodeError):return self.reply({'error':'json'},400)
   if not isinstance(row,dict):return self.reply({'error':'object'},400)
   if self.path=='/telemetry':record(row);return self.reply({'ok':True})
   if self.path=='/control':
    row['server_sent_ms']=time.monotonic_ns()/1e6
    try:commands.put_nowait(row)
    except queue.Full:return self.reply({'error':'queue full'},429)
    record({'type':'command_sent','event':row});return self.reply({'queued':True})
   return self.reply({'error':'path'},404)
 server=ThreadingHTTPServer(('127.0.0.1',a.port),Handler);server.daemon_threads=True
 print(json.dumps({'port':a.port,'model_requests':0,'no_inference_ack':True}),flush=True)
 server.serve_forever()
if __name__=='__main__':main()
