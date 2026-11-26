"""Replay final deterministic display rules over the recorded baseline, no inference."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'evaluation/results/accuracy-style-20261019'


def main():
    manifest = json.loads((OUT / 'manifest.json').read_text())
    raw = [json.loads(s) for s in (OUT / 'requests.jsonl').read_text().splitlines()]
    inputs = [r for r in raw if r['type'] == 'request' and r['arm'] == 'standard']
    texts = {c['id']: c for c in manifest['text_cases']}
    process = subprocess.Popen(['/home/hyh/Tools/java/eclipse-temurin-jdk17/bin/java', '-Xmx64m',
        '-cp', (OUT / 'final_render_classpath.txt').read_text(), 'CaptionStyleReplay'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    rows = []
    try:
        for r in inputs:
            if r['modality'] == 'audio' and r['status'] != 'subtitle':
                continue
            english = r.get('english', texts.get(r['case_id'], {}).get('english', ''))
            for style in ['standard', 'natural', 'community']:
                enc = lambda s: base64.b64encode(s.encode()).decode()
                process.stdin.write('\t'.join([enc(english), enc(r['chinese']), style,
                    str(style == 'community').lower(), 'true', 'true']) + '\n')
                process.stdin.flush()
                f = process.stdout.readline().strip().split('\t')
                if len(f) != 4:
                    raise RuntimeError('Renderer bridge failed')
                rows.append(dict(case_id=r['case_id'], modality=r['modality'], style=style,
                    english=english, original=r['chinese'], chinese=base64.b64decode(f[0]).decode(),
                    nicknames=int(f[1]), playful=f[2] == 'true', localized_phrases=int(f[3])))
    finally:
        process.stdin.close()
        assert process.wait(timeout=10) == 0
    summary = dict(model_requests=0, audio_baseline_subtitles=20, text_cases=12,
        audio_prompts_unchanged='Final native JUnit verifies every style/task equals original E2eProtocol.systemFor.',
        note='Known-cache deterministic display replay; does not prove new acoustic accuracy or human preference.',
        arms={})
    for style in ['standard', 'natural', 'community']:
        for modality in ['audio', 'text']:
            selected = [r for r in rows if r['style'] == style and r['modality'] == modality]
            summary['arms'][style+'_'+modality] = dict(rows=len(selected),
                changed=sum(r['chinese'] != r['original'] for r in selected),
                nickname_labels=sum(r['nicknames'] for r in selected),
                playful=sum(r['playful'] for r in selected),
                localized_phrases=sum(r['localized_phrases'] for r in selected))
    files = [ROOT/'evaluation/caption_style_replay.py', ROOT/'evaluation/CaptionStyleReplay.java',
             ROOT/'android/app/src/main/kotlin/dev/opencaption/opencaption/CaptionStyle.kt']
    summary['files'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    (OUT / 'final_style_replay.json').write_text(json.dumps(dict(rows=rows, summary=summary), ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
