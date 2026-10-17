"""One bounded, no-retry model process for the real Dart controller probe."""
import contextlib
import base64
import hashlib
import json
from pathlib import Path
import sys
import subprocess
import time

from v020_runtime_validation import OUT, Protocol, runtime, append


def emit(value):
    print('OPENCAPTION_JSON ' + json.dumps(value, ensure_ascii=False), flush=True)


def main():
    manifest_path = OUT / 'controller_closed_loop_manifest.json'
    manifest = json.loads(manifest_path.read_text())
    output = OUT / 'controller_closed_loop_model.jsonl'
    if output.exists():
        raise RuntimeError('Probe already started; inspect checkpoint, never retry implicitly')
    for path, digest in {**manifest['sources'], **manifest['classes']}.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != digest:
            raise RuntimeError('Frozen product source changed: ' + path)
    for case in manifest['cases']:
        if hashlib.sha256(Path(case['path']).read_bytes()).hexdigest() != case['sha256']:
            raise RuntimeError('Frozen audio changed')
    append(output, dict(type='metadata', manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
                        scope=manifest['scope'], config=dict(context=768, output=128, threads=4)))
    protocol = Protocol()
    cp = (OUT.parent / 'v020-jvm/protocol-classpath.txt').read_text()
    cadence = subprocess.Popen(['/home/hyh/Tools/java/eclipse-temurin-jdk17/bin/java',
        '-Xmx64m', '-cp', cp, 'V020HintDecisionBridge'], stdin=subprocess.PIPE,
        stdout=subprocess.PIPE, text=True)
    model = None
    count = 0
    try:
        with contextlib.redirect_stdout(sys.stderr):
            model = runtime()
        emit(dict(type='ready'))
        for mode in manifest['modes']:
            for case in manifest['cases']:
                line = sys.stdin.readline()
                if not line:
                    raise RuntimeError('Controller ended before all frozen requests')
                request = json.loads(line)
                if request['mode'] != mode or request['window'] != case['window']:
                    raise RuntimeError('Out-of-order controller request')
                hints = request['hints']
                if not isinstance(hints, str) or len(hints) > 240 or (mode == 'no_hint' and hints):
                    raise ValueError('Unexpected hints/budget')
                requested_hints = hints
                cadence.stdin.write(f"{case['window']}\t{str(mode == 'automatic').lower()}\t" +
                    base64.b64encode(hints.encode()).decode() + '\n')
                cadence.stdin.flush()
                fields = cadence.stdout.readline().rstrip('\r\n').split('\t')
                hints = base64.b64decode(fields[0]).decode()
                model.system_message, model.prompt = protocol.prompt('bilingual', hints)
                began = time.monotonic()
                with contextlib.redirect_stdout(sys.stderr):
                    raw = model.infer(Path(case['path']))
                row = dict(type='request', mode=mode, window=case['window'],
                           start_ms=case['start_ms'], end_ms=case['end_ms'], hints=hints,
                           requested_hints=requested_hints, verification=fields[1] == 'true',
                           inference_ms=(time.monotonic()-began)*1000, raw=raw,
                           **protocol.parse('bilingual', raw))
                append(output, row)
                emit(row)
                count += 1
        append(output, dict(type='complete', requests=count))
        emit(dict(type='complete', requests=count))
    finally:
        if model is not None:
            model.close()
        protocol.close()
        cadence.stdin.close()
        cadence.wait(timeout=10)


if __name__ == '__main__':
    main()
