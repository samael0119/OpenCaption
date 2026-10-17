"""Single follow-up guard for the one frozen input-padding candidate."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from v020_runtime_validation import ROOT, OUT, Protocol, runtime, infer, append
from v020_short_answer_validation import score


def main():
    path=OUT/'short_padding_guard_manifest.json'
    manifest=json.loads(path.read_text())
    output=OUT/'short_padding_guard.jsonl'
    if output.exists():
        raise RuntimeError('Guard already started; inspect instead of retry')
    for file,digest in manifest['classes'].items():
        assert hashlib.sha256(Path(file).read_bytes()).hexdigest()==digest
    for case in manifest['cases']:
        for prefix in ['','padded_']:
            assert hashlib.sha256((ROOT/case[prefix+'path']).read_bytes()).hexdigest()==case[prefix+'sha256']
    append(output,dict(type='metadata',manifest_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        utc=datetime.now(timezone.utc).isoformat(),scope=manifest['scope'],acceptance=manifest['acceptance']))
    protocol=Protocol();model=runtime();rows=[]
    try:
        for case in manifest['cases']:
            # Critical unpadded outputs already exist; do not duplicate them.
            for mode in (['leading2s'] if case['kind']!='instrumental_music' else ['original','leading2s']):
                input_case={**case,'path':case['padded_path'] if mode=='leading2s' else case['path']}
                row=infer(model,protocol,input_case,'bilingual','');row['input_mode']=mode
                if 'label' in case:
                    row.update(score(row,case))
                rows.append(row);append(output,dict(type='request',**row))
        append(output,dict(type='complete',requests=len(rows)))
    finally:
        model.close();protocol.close()
    music=[r for r in rows if r['kind']=='instrumental_music']
    critical=[r for r in rows if r['kind']!='instrumental_music']
    (OUT/'short_padding_guard_summary.json').write_text(json.dumps(dict(complete=True,requests=len(rows),
        music_outputs=music,critical_outputs=critical,
        music_guard_passed=all(r['status']=='no_speech' for r in music),
        critical_errors_resolved=all(r['joint_keyword_ok'] for r in critical),
        scope=manifest['scope'],product_enabled=False),ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':
    main()
