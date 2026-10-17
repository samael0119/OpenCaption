"""Real-clock product-core integration adapter; no quality gold or phone.

JVM capture/VAD/queue keeps running while the one resident model works.
Dart acknowledges only after its real controller and widget have received the
result. Android backend, AudioRecord/Handler/watchdog are outside this adapter.
"""
import base64
import contextlib
import hashlib
import json
import os
from pathlib import Path
import queue
import resource
import subprocess
import sys
import threading
import time

from v020_runtime_validation import runtime, OUT, MODEL
from v020_bridge_transport import split_response


def main():
    name = os.environ['OPENCAPTION_JOINT_RUN']
    manifest_path = OUT / 'joint_live_manifest.json'
    manifest = json.loads(manifest_path.read_text())
    config = manifest['runs'][name]
    output = OUT / f'joint_live_{name}_model.jsonl'
    if output.exists():
        raise RuntimeError('Existing run: inspect checkpoint; no implicit retry')
    for path, digest in manifest['files'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise RuntimeError('Frozen source/input/class mismatch: ' + path)
    model_digest = hashlib.sha256()
    with MODEL.open('rb') as source:
        for block in iter(lambda: source.read(8*1024*1024), b''):
            model_digest.update(block)
    if model_digest.hexdigest() != manifest['model_sha256']:
        raise RuntimeError('Frozen model mismatch')
    lock = threading.Lock()
    # redirect_stdout is process-global: bind the transport before model logs
    # are redirected, otherwise concurrent capture events disappear to stderr.
    transport_stdout = sys.stdout
    def log(row):
        with lock:
            with output.open('a') as f:
                f.write(json.dumps(row, ensure_ascii=False)+'\n')
    def emit(row):
        with lock:
            print('OPENCAPTION_JSON '+json.dumps(row, ensure_ascii=False), file=transport_stdout, flush=True)
    log(dict(type='metadata', name=name, config=config,
             manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
             scope=manifest['scope'], model_sha256=manifest['model_sha256']))
    relative = Path('/proc/self/cgroup').read_text().strip().split('::', 1)[1]
    cgroup = Path('/sys/fs/cgroup') / relative.lstrip('/')
    def memory():
        return {key: (cgroup/key).read_text().strip() for key in
                ('memory.current', 'memory.peak', 'memory.max', 'memory.swap.current',
                 'memory.swap.max', 'memory.events')}
    limits = memory()
    if limits['memory.max'] != str(6144*1024*1024) or limits['memory.swap.max'] != '0':
        raise RuntimeError('Expected 6GiB memory max and swap disabled')
    log(dict(type='resources', cgroup=str(cgroup), **limits))
    # Separate Java handles, both bounded and in the same model cgroup.
    java = '/home/hyh/Tools/java/eclipse-temurin-jdk17/bin/java'
    cp = manifest['classpath']
    protocol = subprocess.Popen([java, '-Xmx64m', '-cp', cp,
        'V020JointProtocolBridge', str(OUT/'joint_live_names.txt')],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    model = None
    capture = None
    try:
        with contextlib.redirect_stdout(sys.stderr):
            model = runtime()
        capture = subprocess.Popen([java, '-Xmx192m', '-cp', cp,
            'V020JointCaptureBridge', str(Path.cwd()), str(OUT/'joint_live_cycle.wav'),
            str(OUT/f'joint_live_{name}_input.wav'), str(config['seconds'])],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        commands_lock = threading.Lock()
        def command(line):
            with commands_lock:
                capture.stdin.write(line+'\n'); capture.stdin.flush()
        requests = queue.Queue(maxsize=2)
        def reader():
            try:
                for line in capture.stdout:
                    f = line.rstrip('\r\n').split('\t')
                    if f[0] == 'REQ':
                        row = dict(type='request_start', window=int(f[1]), start_ms=int(f[2]),
                            end_ms=int(f[3]), started_ms=int(f[4]), submitted_ms=int(f[5]),
                            source_samples=int(f[6]), input_samples=int(f[7]),
                            hints=base64.b64decode(f[8]).decode(), verification=f[9]=='true')
                        requests.put(row, timeout=5)
                    elif f[0] == 'ERR':
                        raise RuntimeError(base64.b64decode(f[1]).decode())
                    else:
                        row = dict(type='capture_event', event=f[0], fields=f[1:])
                        if f[0] == 'ACT': row['resources'] = memory()
                        log(row); emit(row)
                        if f[0] == 'END':
                            requests.put(None); return
                raise RuntimeError('Capture ended without completion')
            except Exception as error:
                requests.put(error)
        def commands():
            try:
                for line in sys.stdin:
                    row = json.loads(line)
                    if row['type'] == 'begin': command('BEGIN')
                    elif row['type'] == 'hints':
                        value = row['hints']
                        if len(value)>240: raise ValueError('hint character budget')
                        command('HINT\t'+base64.b64encode(value.encode()).decode()+'\t'+str(row['automatic']).lower())
                    elif row['type'] == 'ack': command('ACK')
                    else: raise ValueError('unknown Dart command')
            except Exception as error:
                requests.put(error)
        threading.Thread(target=reader, daemon=True).start()
        threading.Thread(target=commands, daemon=True).start()
        emit(dict(type='ready', name=name, seconds=config['seconds'], actions=config['actions']))
        count=0
        while True:
            row=requests.get(timeout=150)
            if row is None: break
            if isinstance(row, Exception): raise row
            log(row)
            hints64=base64.b64encode(row['hints'].encode()).decode()
            protocol.stdin.write('prompt\tbilingual\t'+hints64+'\n'); protocol.stdin.flush()
            fields=split_response(protocol.stdout.readline())
            model.system_message, model.prompt = [base64.b64decode(f).decode() for f in fields]
            began=time.monotonic()
            with contextlib.redirect_stdout(sys.stderr):
                raw=model.infer(OUT/f'joint_live_{name}_input.wav')
            inference_ms=(time.monotonic()-began)*1000
            # A fixed injected delay makes actual queue pressure visible in smoke,
            # without changing segmentation or duplicating the product queue.
            delay=config['delay_ms'] if row['end_ms']<=config['delay_until_ms'] else 0
            if delay: time.sleep(delay/1000)
            protocol.stdin.write('parse\tbilingual\t'+hints64+'\t'+base64.b64encode(raw.encode()).decode()+'\n'); protocol.stdin.flush()
            fields=split_response(protocol.stdout.readline())
            parsed=dict(status=fields[0], english='', chinese='', reason='')
            if fields[0]=='subtitle': parsed.update(english=base64.b64decode(fields[1]).decode(),chinese=base64.b64decode(fields[2]).decode())
            elif fields[0]=='invalid': parsed['reason']=base64.b64decode(fields[1]).decode()
            row.update(type='result', raw=raw, inference_ms=inference_ms, injected_delay_ms=delay,
                       result_monotonic=time.monotonic(), peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, **parsed)
            log(row); emit(row); count+=1
        if capture.wait(timeout=15)!=0: raise RuntimeError('Capture exit failure')
        row=dict(type='complete', name=name, requests=count, independent_quality_acceptance=False)
        log(row); emit(row)
    finally:
        if capture is not None:
            if capture.poll() is None: capture.kill()
            capture.wait(timeout=15)
        if model is not None: model.close()
        protocol.stdin.close(); protocol.wait(timeout=10)


if __name__ == '__main__':
    main()
