"""Evidence bookkeeping for a single bounded post-stability local job."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'evaluation/results/v020-independent'


def digest(path):
    sha = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            sha.update(chunk)
    return sha.hexdigest()


def sources():
    paths = []
    for folder in ['lib','test','pigeons','android/app/src','assets']:
        paths.extend(p for p in (ROOT/folder).rglob('*') if p.is_file())
    paths.extend(ROOT/p for p in ['pubspec.yaml','pubspec.lock','android/app/build.gradle.kts',
        'android/gradle.properties','android/settings.gradle.kts','scripts/flutterw',
        'scripts/build-local-ui-preview','evaluation/V020ProtocolBridge.java',
        'evaluation/V020SpeechEvidenceProbe.java','evaluation/v020_short_answer_validation.py',
        'evaluation/v020_runtime_validation.py','evaluation/v020_speech_evidence_summary.py',
        'evaluation/v020_bridge_transport.py',
        'evaluation/v020_post_pipeline_state.py','scripts/run-v020-after-stability',
        'scripts/run-v020-short-answers','scripts/run-v020-speech-evidence'])
    return {str(p.relative_to(ROOT)):digest(p) for p in sorted(set(paths))}


def stamp():
    return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()


def main():
    action = sys.argv[1]
    snapshot = OUT/'post_source_snapshot.json'
    if action == 'snapshot':
        if snapshot.exists():
            raise RuntimeError('Existing pipeline snapshot; inspect before resuming')
        snapshot.write_text(json.dumps(dict(at=stamp(), sources=sources()),ensure_ascii=False,indent=2)+'\n')
    elif action == 'check':
        expected = json.loads(snapshot.read_text())['sources']
        actual = sources()
        changed = sorted(k for k in expected.keys()|actual.keys() if expected.get(k)!=actual.get(k))
        if changed:
            raise RuntimeError('Source changed during validation: '+', '.join(changed))
    elif action == 'event':
        row = dict(at=stamp(),phase=sys.argv[2],state=sys.argv[3])
        with (OUT/'post_pipeline.jsonl').open('a') as log:
            log.write(json.dumps(row,ensure_ascii=False)+'\n')
        if row['state'] != 'start':
            with (ROOT/'docs/dev/v0.2.0执行检查点.md').open('a') as doc:
                doc.write(f"\n- 本机后续流水线 {row['at']}：`{row['phase']}` → `{row['state']}`；日志见 evaluation/results/v020-independent/post_pipeline.jsonl。阶段成功不代表整版验收。\n")
    elif action == 'artifact':
        apk = ROOT/'build/app/outputs/flutter-apk/app-gemmae2e-debug.apk'
        value = dict(at=stamp(),apk=str(apk),apk_sha256=digest(apk),apk_bytes=apk.stat().st_size,
                     source_snapshot=str(snapshot), scope='Unreleased local candidate; no install/Android performance claim')
        (OUT/'post_apk_snapshot.json').write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
        with (ROOT/'docs/dev/archive/v0.2.0晨间报告.md').open('a') as doc:
            doc.write(f"\n## 本机流水线候选更新 {value['at']}\n\n新候选APK已构建并完成签名检查，SHA256 `{value['apk_sha256']}`，{value['apk_bytes']}字节；覆盖上方03:10产物哈希，源快照与测试日志见 evaluation/results/v020-independent/post_apk_snapshot.json / post_source_snapshot.json / post_pipeline.jsonl。其他质量关口仍以报告判定，未发布、未安装。\n")
    else:
        raise ValueError(action)


if __name__ == '__main__':
    main()
