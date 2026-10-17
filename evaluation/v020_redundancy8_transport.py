"""File-command transport after zero-call PTY job-control failure; same candidate."""
import json,pathlib,sys,time
import v020_redundancy8 as x
class Commands:
 def __iter__(self):
  for batch in range(9):
   p=x.O/'commands'/str(batch);end=time.monotonic()+180
   while not p.exists():
    x.guard()
    if time.monotonic()>end:raise TimeoutError('No fresh batch command in180s')
    time.sleep(.25)
   if p.read_text().strip()!=f'batch {batch}':raise RuntimeError('Bad command')
   yield f'batch {batch}\n'
if __name__=='__main__':
 m=x.read(x.O/'transport_manifest.json')
 for p,h in m['files'].items():assert x.sha(x.R/p)==h,p
 sys.stdin=Commands();x.serve()
