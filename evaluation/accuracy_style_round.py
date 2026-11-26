"""Bounded local development screen. Never treats synthetic/reference text as ASR gain."""
import argparse
import array
import base64
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'evaluation/results/accuracy-style-20261019'
JAVA = '/home/hyh/Tools/java/eclipse-temurin-jdk17/bin/java'
MODEL = Path('/home/hyh/Tools/litert/models/gemma-4-E2B-it.litertlm')
MEANING_RULE = (' Translate the meaning supported by the audio, not a clear transcription error. '
                'Use context only to resolve acoustically plausible ambiguity. '
                'Never infer a name, action, number or negation from context alone.')
TEXT_SYSTEM = ('Translate the English into Mainland Simplified Chinese. Preserve names, numbers, '
               'negation, participants and uncertainty. Output only the translation. Do not add facts.')


def read(path):
    return json.loads(path.read_text())


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for part in iter(lambda: f.read(1024 * 1024), b''):
            h.update(part)
    return h.hexdigest()


def put(name, value):
    with (OUT / name).open('x') as f:
        json.dump(value, f, ensure_ascii=False, indent=2)


def append(value):
    with (OUT / 'requests.jsonl').open('a') as f:
        f.write(json.dumps(value, ensure_ascii=False) + '\n')


def resources():
    group = next(s for s in Path('/proc/self/cgroup').read_text().splitlines() if s.startswith('0::'))
    p = Path('/sys/fs/cgroup') / group.split('::', 1)[1].lstrip('/')
    result = {key: (p / key).read_text().strip() for key in
              ['memory.max', 'memory.swap.max', 'memory.swap.current', 'memory.peak', 'memory.events']}
    if result['memory.max'] == 'max' or int(result['memory.max']) > 6 * 1024**3 or result['memory.swap.max'] != '0':
        raise RuntimeError('Requires <=6GiB cgroup and swap disabled')
    return result


class Bridge:
    def __init__(self):
        self.p = subprocess.Popen([JAVA, '-Xmx64m', '-cp', (OUT / 'classpath.txt').read_text(),
                                   'CaptionRoundBridge'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)

    @staticmethod
    def enc(value):
        return base64.b64encode(value.encode()).decode()

    @staticmethod
    def dec(value):
        return base64.b64decode(value).decode()

    def call(self, *fields):
        self.p.stdin.write('\t'.join(fields) + '\n')
        self.p.stdin.flush()
        line = self.p.stdout.readline()
        if not line:
            raise RuntimeError('JVM bridge exited')
        return line.rstrip('\n').split('\t')

    def prompt(self, style):
        return [self.dec(x) for x in self.call('prompt', style)]

    def parse(self, raw):
        f = self.call('parse', self.enc(raw))
        result = dict(status=f[0], english='', chinese='')
        if f[0] == 'subtitle':
            result.update(english=self.dec(f[1]), chinese=self.dec(f[2]))
        elif f[0] == 'invalid':
            result['reason'] = self.dec(f[1])
        return result

    def render(self, english, chinese):
        f = self.call('render', self.enc(english), self.enc(chinese), 'community', 'true')
        return dict(chinese=self.dec(f[0]), nicknames=int(f[1]), playful=f[2] == 'true')

    def close(self):
        self.p.stdin.close()
        if self.p.wait(timeout=10) != 0:
            raise RuntimeError('JVM bridge failed')


def prepare():
    if (OUT / 'manifest.json').exists() or (OUT / 'requests.jsonl').exists():
        raise RuntimeError('Already frozen; do not overwrite')
    OUT.mkdir(exist_ok=True)
    prior = read(ROOT / 'evaluation/results/v020-redundancy8/P0_manifest.json')
    diagnostic = read(ROOT / 'evaluation/results/v020-diagnostic11/manifest.json')
    compiler = read(ROOT / 'evaluation/results/v020-integrity8/manifest.json')['compiler_files']
    for path, digest in compiler.items():
        assert sha(Path(path)) == digest
    cp = list(compiler)
    classes = OUT / 'classes'
    classes.mkdir(exist_ok=True)
    native = ROOT / 'android/app/src/main/kotlin/dev/opencaption/opencaption'
    from v020_pcm10_prepare import extract
    backend = ROOT / 'android/app/src/gemmaE2E/kotlin/dev/opencaption/opencaption/FlavorBackendFactory.kt'
    method = extract(backend.read_text(), 'private fun wav(samples: FloatArray): ByteArray')
    source = ('import java.nio.ByteBuffer\nimport java.nio.ByteOrder\nimport java.io.File\n'
              'import dev.opencaption.opencaption.E2eAudioInput\nobject RoundInput {\n' + method + '\n'
              '@JvmStatic fun main(args:Array<String>){val b=File(args[0]).readBytes();'
              'val p=ByteBuffer.wrap(b).order(ByteOrder.LITTLE_ENDIAN);'
              'val x=FloatArray(b.size/2){p.short/32768f};'
              'File(args[1]).writeBytes(wav(E2eAudioInput.prepareShort(x)))}}\n')
    (OUT / 'RoundInput.kt').write_text(source)
    sources = [native / f'{s}.kt' for s in ['E2eProtocol', 'E2ePreservedNames', 'E2eAudioInput', 'CaptionStyle']]
    sources.append(OUT / 'RoundInput.kt')
    subprocess.run([JAVA, '-Xmx256m', '-cp', ':'.join(cp), 'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler',
                    '-no-stdlib', '-no-reflect', '-jvm-target', '17', '-classpath', ':'.join(cp[1:]),
                    '-d', str(classes), *map(str, sources)], check=True)
    runtime = str(classes) + ':' + cp[1]
    subprocess.run([str(Path(JAVA).with_name('javac')), '-cp', runtime, '-d', str(classes),
                    str(ROOT / 'evaluation/CaptionRoundBridge.java')], check=True)
    (OUT / 'classpath.txt').write_text(runtime)
    bridge = Bridge()
    try:
        standard, request = bridge.prompt('standard')
        natural, _ = bridge.prompt('natural')
    finally:
        bridge.close()
    selected = [c for c in prior['cases'] if c['group'] in ['fleurs_semantic', 'music', 'known_short_music']]
    selected += [c for c in prior['cases'] if c['group'] == 'natural_whisper'][:5]
    cases = [dict(id=str(c['id']), group=c['group'], reference_en=c.get('reference_en', ''),
                  semantic_units=c.get('semantic_units', [c.get('reference_en', '')]),
                  original_path=c['path'], original_sha256=c['sha256'], primary=True) for c in selected]
    cases += [dict(id=str(c['id']), group='diagnostic11', reference_en=c['reference_en'],
                   semantic_units=c['semantic_units'], original_path=c['audio_path'],
                   original_sha256=c['audio_sha256'], primary=c['primary']) for c in diagnostic['cases']]
    assert len(cases) == 24 and len({c['id'] for c in cases}) == 24
    audio = OUT / 'audio'
    audio.mkdir(exist_ok=True)
    for c in cases:
        original = ROOT / c['original_path']
        assert sha(original) == c['original_sha256']
        with wave.open(str(original), 'rb') as f:
            assert f.getparams()[:3] == (1, 2, 16000)
            data = f.readframes(f.getnframes())
        pcm = audio / (c['id'] + '.pcm')
        pcm.write_bytes(data)
        target = audio / (c['id'] + '.wav')
        subprocess.run([JAVA, '-Xmx64m', '-cp', runtime, 'RoundInput', str(pcm), str(target)], check=True)
        c.update(path=str(target.relative_to(ROOT)), sha256=sha(target), samples=len(data) // 2)
    text_cases = read(OUT / 'text_cases.json')
    assert len(text_cases) == 12
    order = []
    for i, c in enumerate(cases):
        arms = ['standard', 'natural', 'meaning_natural']
        arms = arms[i % 3:] + arms[:i % 3]
        for arm in arms:
            order.append(dict(index=len(order), case_id=c['id'], modality='audio', arm=arm))
    for i, c in enumerate(text_cases):
        for arm in (['standard', 'natural'] if i % 2 == 0 else ['natural', 'standard']):
            order.append(dict(index=len(order), case_id=c['id'], modality='text', arm=arm))
    prompts = dict(standard=standard, natural=natural, meaning_natural=natural + MEANING_RULE,
                   request=request, text_standard=TEXT_SYSTEM,
                   text_natural=TEXT_SYSTEM + natural[len(standard):])
    score = dict(scope='Known development audio and constructed text; AI-assisted ratings, no independent preference/gold claims.',
                 primary_speech_cases=17, all_speech_cases=19, music_cases=5,
                 excluded_primary_ids=['1908', '1978'], states=['preserved', 'omitted', 'contradicted', 'uncertain'],
                 whole_sentence='All required facts, identity/negation/numbers preserved and no unsupported additions.',
                 continuation=dict(whole_gain_pp=5, target_error_reduction=.20, net_repairs_min=3,
                                   different_recordings_min=3, new_critical_errors=0, coverage_nondecreasing=True),
                 latency='Service proxy only, n24; no formal P95 or physical display claims.',
                 style='Report facts, identities, unlicensed humor and AI-assisted naturalness separately; no human preference percentage.')
    put('score_spec.json', score)
    paths = sources + [backend, ROOT / 'evaluation/accuracy_style_round.py', ROOT / 'evaluation/CaptionRoundBridge.java',
                       ROOT / 'evaluation/gemma_replay.py', ROOT / 'evaluation/v020_pcm10_prepare.py',
                       OUT / 'classpath.txt', OUT / 'score_spec.json', OUT / 'text_cases.json']
    paths += list(classes.rglob('*.class')) + [ROOT / c['path'] for c in cases]
    import litert_lm
    paths += list(Path(litert_lm.__file__).parent.rglob('*.py'))
    files = {str(p): sha(p) for p in paths}
    put('manifest.json', dict(base_commit=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        files=files, model=str(MODEL), model_sha256=sha(MODEL), prompts=prompts, cases=cases,
        text_cases=text_cases, order=order, config=dict(context=768, output=128, threads=4, thinking=False,
        top_k=1, temperature=0, backend='Linux CPU', speculative_decoding=None), bounds=dict(requests=96,
        audio_requests=72, text_requests=24, derived_community_rows=12, batch_max=8, retries=0,
        memory_max=6*1024**3, swap=0, timeout_seconds=900), score=score,
        model_override='User explicitly authorized current conversation model for this round.',
        phonetic_gain_not_tested='No independently verified pronunciation data; no phonetic arm or claimed gain.'))
    print('Frozen: 72 audio + 24 text requests, 12 derived community rows. Zero model initializations.', flush=True)


def verify():
    m = read(OUT / 'manifest.json')
    for path, digest in m['files'].items():
        if sha(Path(path)) != digest:
            raise RuntimeError('Frozen dependency changed: ' + path)
    if sha(MODEL) != m['model_sha256']:
        raise RuntimeError('Model changed')
    return m


def serve():
    m = verify()
    if (OUT / 'requests.jsonl').exists():
        raise RuntimeError('No restart or answer retries')
    limits = resources()
    quota = read(OUT / 'quota.json')
    if not 0 <= time.time() - quota['at_unix'] < 180 or quota['weekly_used'] >= 60 or quota['five_hour_used'] >= 100:
        raise RuntimeError('Fresh quota required')
    import litert_lm as api
    from gemma_replay import response_text
    bridge = Bridge()
    model = None
    append(dict(type='metadata', manifest_sha256=sha(OUT / 'manifest.json'), resources=limits, quota=quota))
    try:
        t = time.monotonic()
        (OUT / 'cache').mkdir(exist_ok=True)
        model = api.Engine(str(MODEL), backend=api.Backend.CPU(thread_count=4),
                           audio_backend=api.Backend.CPU(thread_count=4), max_num_tokens=768,
                           cache_dir=str(OUT / 'cache'), enable_speculative_decoding=None)
        append(dict(type='loaded', load_ms=(time.monotonic()-t)*1000, resources=resources()))
        print('READY', flush=True)
        audio = {c['id']: c for c in m['cases']}
        texts = {c['id']: c for c in m['text_cases']}
        for batch in range(12):
            command = OUT / 'commands' / str(batch)
            deadline = time.monotonic() + 180
            while not command.exists():
                if time.monotonic() > deadline:
                    raise TimeoutError('No next numbered batch command within 180s')
                time.sleep(.1)
            if command.read_text().strip() != f'batch {batch}':
                raise RuntimeError('Expected next numbered file command')
            q = read(OUT / 'quota.json')
            if not 0 <= time.time()-q['at_unix'] < 180 or q['weekly_used'] >= 60 or q['five_hour_used'] >= 100:
                raise RuntimeError('Quota expired or exhausted')
            for item in m['order'][batch*8:(batch+1)*8]:
                c = (audio if item['modality'] == 'audio' else texts)[item['case_id']]
                append(dict(type='started', **item))
                if item['modality'] == 'audio':
                    system = m['prompts'][item['arm']]
                    content = api.Contents.of(m['prompts']['request'], api.Content.AudioFile(str(ROOT/c['path'])))
                else:
                    system = m['prompts']['text_'+item['arm']]
                    content = api.Contents.of(c['english'])
                t = time.monotonic()
                with model.create_conversation(system_message=system, thinking_config=api.ThinkingConfig(False, 0),
                     sampler_config=api.SamplerConfig(top_k=1, top_p=1.0, temperature=0.0), max_output_tokens=128) as conversation:
                    raw = response_text(conversation.send_message(content, max_output_tokens=128,
                                            thinking_config=api.ThinkingConfig(False, 0)))
                elapsed = (time.monotonic()-t)*1000
                parsed = bridge.parse(raw) if item['modality'] == 'audio' else dict(chinese=raw.strip())
                row = dict(type='request', **item, raw=raw, inference_ms=elapsed, **parsed)
                if item['modality'] == 'text' and item['arm'] == 'natural':
                    row['derived_community'] = bridge.render(c['english'], raw.strip())
                append(row)
            append(dict(type='batch_complete', batch=batch, done=(batch+1)*8, resources=resources()))
            print(f'BATCH_COMPLETE {batch}', flush=True)
        append(dict(type='complete', requests=96, resources=resources()))
        print('COMPLETE96', flush=True)
    except BaseException as e:
        append(dict(type='failure', error=repr(e)))
        raise
    finally:
        if model is not None:
            model.close()
        bridge.close()
        append(dict(type='closed', resources=resources()))


if __name__ == '__main__':
    action = argparse.ArgumentParser()
    action.add_argument('command', choices=['prepare', 'verify', 'serve'])
    command = action.parse_args().command
    {'prepare': prepare, 'verify': verify, 'serve': serve}[command]()
