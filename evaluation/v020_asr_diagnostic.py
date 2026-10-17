"""One pinned base.en source-only comparison, no product/model-route switch."""
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import resource
import subprocess
import time

from score_reference import words, edit_distance
from v020_short_answer_validation import normalized, NUMBERS

ROOT=Path(__file__).resolve().parents[1]
ASR=ROOT/'evaluation/results/v020-asr-preflight'


def main():
    manifest_path=ASR/'diagnostic_manifest.json'
    manifest=json.loads(manifest_path.read_text())
    output=ASR/'diagnostic.jsonl'
    if output.exists():
        raise RuntimeError('Diagnostic already started; inspect instead of implicit retry')
    for key in ['binary','model']:
        if hashlib.sha256((ROOT/manifest[key]).read_bytes()).hexdigest()!=manifest[key+'_sha256']:
            raise RuntimeError('Frozen '+key+' changed')
    for case in manifest['cases']:
        if hashlib.sha256((ROOT/case['path']).read_bytes()).hexdigest()!=case['sha256']:
            raise RuntimeError('Frozen audio changed')
    results_dir=ASR/'outputs';results_dir.mkdir(exist_ok=False)
    command=[str(ROOT/manifest['binary']),'-m',str(ROOT/manifest['model']),*manifest['args']]
    for index,case in enumerate(manifest['cases']):
        command += ['-f',str(ROOT/case['path']),'-of',str(results_dir/f'{index:03}')]
    def append(row):
        with output.open('a') as f:
            f.write(json.dumps(row,ensure_ascii=False)+'\n')
    append(dict(type='metadata',utc=datetime.now(timezone.utc).isoformat(),
        manifest_sha256=hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        scope=manifest['scope'],single_process=True,keyword_prompt=False))
    began=time.monotonic()
    with (ASR/'cli_stdout.log').open('w') as stdout,(ASR/'cli_stderr.log').open('w') as stderr:
        result=subprocess.run(command,stdout=stdout,stderr=stderr,timeout=550)
    if result.returncode:
        append(dict(type='failed',exit_code=result.returncode))
        raise RuntimeError('ASR CLI failed; keep partial outputs, no implicit rerun')
    elapsed=time.monotonic()-began
    rows=[]
    for index,case in enumerate(manifest['cases']):
        path=results_dir/f'{index:03}.json'
        document=json.loads(path.read_text())
        text=' '.join(s['text'].strip() for s in document['transcription']).strip()
        family='short' if 'label' in case else 'music' if case['kind']=='instrumental_music' else 'whisper'
        row=dict(type='request',index=index,case_id=case['id'],family=family,text=text,
            result_file=str(path.relative_to(ROOT)),result_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        if family=='short':
            row['source_keyword_ok']=normalized(text) in {case['label'],NUMBERS.get(case['label'],case['label'])}
        elif family=='whisper':
            ref=words(case['reference_en']);row.update(exact_command_ok=words(text)==ref,
                reference_words=len(ref),word_errors=edit_distance(ref,words(text)))
        # Keep musical tags and other nonempty outputs as-is. There is no
        # product display path, so do not call this a zero-hallucination pass.
        append(row);rows.append(row)
    append(dict(type='complete',requests=len(rows),elapsed_seconds=elapsed,
        peak_child_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss))
    groups={}
    for family in ['short','whisper','music']:
        selected=[r for r in rows if r['family']==family]
        group=dict(n=len(selected),empty_outputs=sum(not r['text'] for r in selected))
        if family=='short':
            group['source_correct']=sum(r['source_keyword_ok'] for r in selected)
            group['prior_critical']=[r for r in selected if r['case_id'] in ['six-3659fc1c-0','no-0c540988-0']]
        elif family=='whisper':
            group.update(exact_command_correct=sum(r['exact_command_ok'] for r in selected),
                wer=sum(r['word_errors'] for r in selected)/sum(r['reference_words'] for r in selected))
        else:
            group['nonempty_music_outputs']=[r for r in selected if r['text']]
        groups[family]=group
    (ASR/'diagnostic_summary.json').write_text(json.dumps(dict(complete=True,requests=len(rows),groups=groups,
        elapsed_seconds=elapsed,peak_child_rss_kib=resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        scope=manifest['scope'],default_changed=False,chinese_or_cs2_quality_acceptance=False),ensure_ascii=False,indent=2)+'\n')


if __name__=='__main__':
    main()
