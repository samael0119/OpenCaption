"""Read-only resource sampling alongside the existing serial model service.

No models, audio, command lines, or environment values are written to the log.
Sampling starts late in run 1; it cannot reconstruct its initial RSS baseline.
"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
TARGET = str(ROOT / 'evaluation/v020_runtime_validation.py')


def model_pids(proc_root=Path('/proc')):
    found = []
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            args = (entry / 'cmdline').read_bytes().split(b'\0')
            # timeout carries the same script arguments, but its RSS is not
            # the model's RSS. Match the executable before matching arguments.
            if not Path(os.fsdecode(args[0])).name.startswith('python'):
                continue
            if TARGET.encode() in args or b'evaluation/v020_runtime_validation.py' in args:
                if b'stability' in args:
                    found.append(int(entry.name))
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            pass
    return found


def sample(pid):
    proc = Path('/proc') / str(pid)
    status = {}
    for line in (proc / 'status').read_text().splitlines():
        key, _, value = line.partition(':')
        if key in ('VmRSS', 'VmHWM', 'VmSwap', 'Threads'):
            status[key] = int(value.split()[0])
    relative = next(line[3:] for line in (proc / 'cgroup').read_text().splitlines()
                    if line.startswith('0::'))
    group = Path('/sys/fs/cgroup') / relative.lstrip('/')
    def number(name):
        value = (group / name).read_text().strip()
        return value if value == 'max' else int(value)
    events = dict((k, int(v)) for k, v in
                  (line.split() for line in (group / 'memory.events').read_text().splitlines()))
    return dict(pid=pid, rss_kib=status.get('VmRSS'), peak_rss_kib=status.get('VmHWM'),
                swap_kib=status.get('VmSwap'), threads=status.get('Threads'),
                cgroup=relative, memory_current_bytes=number('memory.current'),
                memory_high_bytes=number('memory.high'), memory_max_bytes=number('memory.max'),
                memory_swap_current_bytes=number('memory.swap.current'),
                memory_swap_max_bytes=number('memory.swap.max'), events=events)


def active():
    return subprocess.run(['systemctl', '--user', 'is-active', '--quiet',
                           'opencaption-v020-runtime.service'], check=False).returncode == 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--interval', type=float, default=15)
    parser.add_argument('--seconds', type=int, default=14400)
    args = parser.parse_args()
    if not 1 <= args.interval <= 60 or not 0 < args.seconds <= 14400:
        parser.error('bounded sampling requires interval 1..60s, duration <=4h')
    uid = os.getuid()
    os.environ.setdefault('XDG_RUNTIME_DIR', f'/run/user/{uid}')
    os.environ.setdefault('DBUS_SESSION_BUS_ADDRESS', f'unix:path=/run/user/{uid}/bus')
    start = time.monotonic()
    with args.output.open('x') as log:
        def write(row):
            log.write(json.dumps(dict(utc=datetime.now(timezone.utc).isoformat(),
                                      monotonic=time.monotonic(), **row)) + '\n')
            log.flush()
        write(dict(type='metadata', interval_seconds=args.interval,
                   scope='Actual RSS sampling; late start in stability run 1; no Android claim'))
        while time.monotonic() - start < args.seconds:
            for pid in model_pids():
                try:
                    write(dict(type='sample', **sample(pid)))
                except (OSError, StopIteration, ValueError) as error:
                    write(dict(type='sample_error', pid=pid, error=type(error).__name__))
            if not active():
                write(dict(type='complete', reason='runtime_service_inactive'))
                return
            time.sleep(args.interval)
        write(dict(type='complete', reason='monitor_time_limit'))


if __name__ == '__main__':
    main()
