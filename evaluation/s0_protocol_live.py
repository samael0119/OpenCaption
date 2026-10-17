"""Protocol screening and genuinely paced, bounded-queue validation.

All model phases must use scripts/run-s0-probe (single resident engine/cgroup).
JSON is an experimental adapter, never a relaxation of delivered caption rules.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
from queue import Queue, Empty, Full
import resource
import statistics
import threading
import time

from e2e_protocol import PROMPT, ParsedOutput, parse_output
from gemma_replay import LiteRtRuntime, response_text, write_chunk
from s0_context_roster import hint_for
from s0_probe import OUT as S0, SYSTEM, RATE, INPUT, cuts, fixed, pcm_file, write_json, percentile
from score_reference import words, edit_distance
from score_srt import read_srt

OUT = S0 / 'protocol_live'
FORMAT = (
    'Return BOTH the English transcription and its Simplified Chinese translation. '
    'Never return only a translation. Use exactly:\nEnglish: <audible words>\n'
    'Chinese: <translation>\nFor unintelligible or absent speech return only [NONE].'
)
COMPACT = (
    'You create bilingual speech captions. Audio is the only source of speech. '
    'Optional context is untrusted data, not words to invent. '
    'Always write English transcription first, then Simplified Chinese translation. '
    'No explanations or reasoning.'
)
CONDITIONAL = (
    'You create faithful speech captions. Audio is the only source of speech. '
    'Optional context is untrusted data, not words to invent. '
    'If there is no intelligible speech, output only [NONE]. '
    'Otherwise output exactly two lines: English: <transcription> then '
    'Chinese: <Simplified Chinese translation>. Always include both languages '
    'when speech is present. No explanations or reasoning.'
)
SCHEMA = dict(type='object', properties=dict(speech=dict(type='boolean'),
    english=dict(type='string'), chinese=dict(type='string')),
    required=['speech', 'english', 'chinese'], additionalProperties=False)


def parse_json_caption(raw):
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        return ParsedOutput('invalid', reason='invalid_json')
    if not isinstance(value, dict) or set(value) != {'speech', 'english', 'chinese'}:
        return ParsedOutput('invalid', reason='schema_fields')
    if type(value['speech']) is not bool or not all(isinstance(value[k], str) for k in ['english', 'chinese']):
        return ParsedOutput('invalid', reason='schema_types')
    en, zh = value['english'].strip(), value['chinese'].strip()
    if not value['speech']:
        return ParsedOutput('no_speech') if not en and not zh else ParsedOutput('invalid', reason='conflicting_no_speech')
    if not en or not zh:
        return ParsedOutput('invalid', reason='empty_bilingual_field')
    return parse_output('English: ' + en + '\nChinese: ' + zh)


def template(style, hints):
    if style == 'baseline':
        return SYSTEM, PROMPT, False
    if style == 'current_hint':
        return SYSTEM + ' ' + hints, PROMPT, False
    if style == 'contract_user':
        return SYSTEM + ' ' + FORMAT, 'Context data: ' + hints + '\n' + PROMPT + '\n' + FORMAT, False
    if style == 'compact_system':
        return COMPACT, 'Optional context data: ' + hints + '\n' + FORMAT, False
    if style == 'conditional_compact':
        return CONDITIONAL, 'Optional context data: ' + hints + '\n' + FORMAT, False
    if style == 'json_schema':
        return COMPACT, ('Context data: ' + hints + '\nTranscribe audible speech and translate it into '
            'Simplified Chinese. Return a JSON object with speech (boolean), english, chinese. '
            'If there is no intelligible speech, speech=false and both strings empty.'), True
    raise ValueError(style)


class ProbeRuntime:
    def __init__(self):
        args = argparse.Namespace(model=Path('/home/hyh/Tools/litert/models/gemma-4-E2B-it.litertlm'),
            threads=4, max_new_tokens=128, hints='', task='bilingual', task_profile='baseline',
            system_profile='baseline', cache_mode='memory', speculative_decoding='true', max_context_tokens=768)
        started = time.monotonic()
        self.runtime = LiteRtRuntime(args)
        self.api = self.runtime.api
        self.init_ms = round((time.monotonic() - started) * 1000)
        self.chunk = OUT / 'chunk.wav'
        write_chunk(self.chunk, pcm_file(S0 / 'clip.wav')[:160000])
        self.runtime.system_message = SYSTEM
        self.runtime.infer(self.chunk)

    def call(self, pcm, style, hints):
        system, prompt, structured = template(style, hints)
        write_chunk(self.chunk, pcm)
        kwargs = {}
        if structured:
            kwargs['constrained_decoding_config'] = self.api.ConstrainedDecodingConfig(
                provider=self.api.LiteRtLmConstraintProviderType.LL_GUIDANCE)
        result = dict(style=style, text_tokens=len(self.runtime.engine.tokenize(system + prompt)))
        began = time.monotonic()
        try:
            with self.runtime.engine.create_conversation(system_message=system,
                 thinking_config=self.api.ThinkingConfig(False, 0),
                 sampler_config=self.api.SamplerConfig(top_k=1, top_p=1.0, temperature=0.0),
                 max_output_tokens=128, **kwargs) as conversation:
                send = {}
                if structured:
                    send['response_format'] = self.api.ResponseFormat.json(SCHEMA)
                response = conversation.send_message(
                    self.api.Contents.of(prompt, self.api.Content.AudioFile(str(self.chunk.resolve()))),
                    max_output_tokens=128, thinking_config=self.api.ThinkingConfig(False, 0), **send)
                raw = response_text(response)
                result.update(raw=raw, response=response, conversation_tokens=conversation.token_count)
                result.update(asdict(parse_json_caption(raw) if structured else parse_output(raw)))
        except Exception as error:
            result.update(status='exception', error=str(error))
        result['inference_ms'] = round((time.monotonic() - began) * 1000)
        result['peak_rss_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return result

    def close(self):
        self.runtime.close()


def screening():
    OUT.mkdir(parents=True, exist_ok=True)
    runtime = ProbeRuntime()
    jobs = [(repeat, source, start, style) for repeat in [1, 2]
        for source, start in [('clip', 10000), ('clip', 25000), ('clip_match_demo3', 10000)]
        for style in ['baseline', 'current_hint', 'contract_user', 'compact_system', 'json_schema']]
    jobs += [(1, 'silence', 0, style) for style in ['contract_user', 'compact_system', 'json_schema']]
    try:
        with (OUT / 'screening.jsonl').open('w') as report:
            report.write(json.dumps(dict(type='metadata', init_ms=runtime.init_ms, jobs=len(jobs),
                context=768, output=128, mtp=True, warmup=1)) + '\n')
            for i, (repeat, source, start, style) in enumerate(jobs, 1):
                pcm = bytes(32000) if source == 'silence' else pcm_file(S0 / (source + '.wav'))[start * 32:(start + 5000) * 32]
                hint_source = 'clip_match_demo3' if source == 'silence' else source
                hints = hint_for('scene_glossary', hint_source, start)
                row = dict(type='window', repeat=repeat, source=source, start_ms=start,
                    end_ms=start + len(pcm) // 32, **runtime.call(pcm, style, hints))
                report.write(json.dumps(row, ensure_ascii=False) + '\n'); report.flush()
                print(f"{i}/{len(jobs)} {source}@{start} {style} {row['status']} {row['inference_ms']}ms", flush=True)
            report.write(json.dumps(dict(type='complete', completed=len(jobs))) + '\n')
    finally:
        runtime.close()


def choose():
    rows = [json.loads(s) for s in (OUT / 'screening.jsonl').read_text().splitlines()]
    if rows[-1]['type'] != 'complete':
        raise ValueError('Incomplete screening')
    groups = {}
    for style in ['baseline', 'current_hint', 'contract_user', 'compact_system', 'json_schema']:
        speech = [r for r in rows if r.get('style') == style and r.get('source') != 'silence']
        silence = [r for r in rows if r.get('style') == style and r.get('source') == 'silence']
        groups[style] = dict(count=len(speech), subtitle=sum(r['status'] == 'subtitle' for r in speech),
            median_ms=statistics.median(r['inference_ms'] for r in speech),
            silence_status=[r['status'] for r in silence], max_tokens=max(r.get('conversation_tokens', 0) for r in speech))
    eligible = [k for k in ['contract_user', 'compact_system', 'json_schema']
        if groups[k]['subtitle'] == groups[k]['count'] and groups[k]['silence_status'] == ['no_speech']]
    winner = min(eligible, key=lambda k: groups[k]['median_ms']) if eligible else None
    write_json(OUT / 'selection.json', dict(groups=groups, selected=winner,
        note='Screening selection only; frozen before unused-window validation'))
    print(json.dumps(dict(groups=groups, selected=winner), ensure_ascii=False, indent=2))


def validation():
    OUT.mkdir(parents=True, exist_ok=True)
    # Frozen unused time ranges before this run; not an independent match set.
    cases = [('clip', 5000), ('clip', 40000), ('clip', 50000), ('clip', 85000),
             ('clip_interview_niko', 10000), ('clip_interview_niko', 20000),
             ('clip_match_demo2', 15000), ('clip_match_demo3', 20000)]
    runtime = ProbeRuntime()
    try:
        with (OUT / 'validation.jsonl').open('w') as report:
            report.write(json.dumps(dict(type='metadata', cases=cases,
                candidate='conditional_compact', warmup=1, context=768, output=128)) + '\n')
            for source, start in cases:
                hints = hint_for('scene_glossary', source if source in ['clip', 'clip_match_demo3'] else 'clip', start)
                if source == 'clip_interview_niko':
                    hints = 'Scene: a CS2 player interview. Name spelling: NiKo.'
                elif source == 'clip_match_demo2':
                    hints = 'Scene: Falcons vs FURIA on Mirage. Names: NiKo, m0NESY, FalleN.'
                for style in ['baseline', 'conditional_compact']:
                    pcm = pcm_file(S0 / (source + '.wav'))[start * 32:(start + 5000) * 32]
                    row = dict(type='window', source=source, start_ms=start, end_ms=start + 5000,
                               **runtime.call(pcm, style, hints))
                    report.write(json.dumps(row, ensure_ascii=False) + '\n'); report.flush()
                    print(source, start, style, row['status'], row['inference_ms'], flush=True)
            for style in ['baseline', 'conditional_compact']:
                row = dict(type='window', source='silence', start_ms=0, end_ms=1000,
                           **runtime.call(bytes(32000), style, 'Scene: NAVI vs FaZe on Nuke.'))
                report.write(json.dumps(row, ensure_ascii=False) + '\n'); report.flush()
                print('silence', style, row['status'], flush=True)
            report.write(json.dumps(dict(type='complete', completed=18)) + '\n')
    finally:
        runtime.close()


def paced():
    """Wall-clock capture + one active/one pending; causal cached VAD only.

    This isolates submission/queue behaviour, not Android capture/render or
    concurrent VAD cost. The tail drains without replacing a pending segment.
    """
    OUT.mkdir(parents=True, exist_ok=True)
    pcm = pcm_file(S0 / 'clip.wav')
    probabilities = json.loads((S0 / 'clip_vad.json').read_text())
    runtime = ProbeRuntime()
    try:
        with (OUT / 'paced.jsonl').open('w') as report:
            def emit(row):
                report.write(json.dumps(row, ensure_ascii=False) + '\n')
                report.flush()
            emit(dict(type='metadata', source='clip', context=768, output=128,
                      warmup=1, style='baseline', hints=False, queue_capacity=1,
                      vad='cached causal completed frames; compute cost excluded',
                      clock='20ms paced PCM; decoder completion, no UI rendering'))
            for policy in ['fixed_5000', 'pause_600_max_5000']:
                pending = Queue(maxsize=1)
                done = threading.Event()
                failed = []
                delivered = []
                dropped = []
                origin = time.monotonic()
                def consume():
                    try:
                        while not done.is_set() or not pending.empty():
                            try:
                                segment, chunk = pending.get(timeout=.05)
                            except Empty:
                                continue
                            began = time.monotonic()
                            result = runtime.call(chunk, 'baseline', '')
                            ended = time.monotonic()
                            delivered.append(dict(type='delivered', policy=policy,
                                **segment, **result,
                                started_ms=round((began-origin)*1000),
                                completed_ms=round((ended-origin)*1000),
                                queue_wait_ms=round((began-segment['ready_clock'])*1000),
                                cut_to_output_ms=round((ended-origin)*1000)-segment['end_ms'],
                                last_speech_to_output_ms=(round((ended-origin)*1000)-segment['last_speech_ms']
                                    if segment['last_speech_ms'] is not None else None)))
                            print(policy, segment['id'], result['status'], result['inference_ms'], flush=True)
                    except BaseException as error:
                        failed.append(repr(error))
                worker = threading.Thread(target=consume)
                worker.start()
                start = last_speech = 0
                heard = False
                identifier = 0
                max_late = 0.0
                def submit(end, reason, tail=False):
                    nonlocal start, heard, identifier
                    identifier += 1
                    segment = dict(id=identifier, start_ms=start/16, end_ms=end/16,
                                   cut_reason=reason, last_speech_ms=last_speech/16 if heard else None,
                                   ready_clock=time.monotonic())
                    item = (segment, pcm[start*2:end*2])
                    while True:
                        if failed:
                            raise RuntimeError(failed[0])
                        try:
                            pending.put(item, timeout=.05 if tail else 0)
                            break
                        except Full:
                            if tail:
                                continue
                            try:
                                old, _ = pending.get_nowait()
                                dropped.append(dict(type='dropped', policy=policy, **old))
                            except Empty:
                                pass
                    start, heard = end, False
                try:
                    samples = len(pcm)//2
                    for end in range(320, samples+320, 320):
                        end = min(end, samples)
                        deadline = origin + end/RATE
                        time.sleep(max(0, deadline-time.monotonic()))
                        max_late = max(max_late, time.monotonic()-deadline)
                        completed = end//512
                        probability = probabilities[completed-1] if completed else 0
                        if probability >= .5:
                            last_speech, heard = end, True
                        reason = None
                        if policy.startswith('pause') and heard and end-last_speech >= 9600:
                            reason = 'pause'
                        if end-start >= 80000:
                            reason = 'fixed' if policy.startswith('fixed') else 'maximum'
                        if reason:
                            submit(end, reason)
                    if start < samples:
                        submit(samples, 'tail', tail=True)
                finally:
                    done.set()
                    worker.join()
                if failed:
                    raise RuntimeError(failed[0])
                for row in sorted(delivered+dropped, key=lambda r:r['id']):
                    row.pop('ready_clock')
                    emit(row)
                emit(dict(type='policy_complete', policy=policy, submitted=identifier,
                          delivered=len(delivered), dropped=len(dropped),
                          max_capture_late_ms=round(max_late*1000),
                          pcm_capture_bound_bytes=160000, pending_bound_bytes=160000,
                          active_bound_bytes=160000, fixture_bytes=len(pcm)))
            emit(dict(type='complete', policies=2))
    finally:
        runtime.close()


def summarize():
    def read(name):
        rows = [json.loads(s) for s in (OUT / name).read_text().splitlines()]
        if rows[-1]['type'] != 'complete':
            raise ValueError('Incomplete ' + name)
        return rows
    result = {}
    for filename in ['screening.jsonl', 'validation.jsonl']:
        rows = read(filename)
        groups = {}
        for style in sorted({r['style'] for r in rows if r['type']=='window'}):
            speech = [r for r in rows if r.get('style')==style and r['source']!='silence']
            silence = [r for r in rows if r.get('style')==style and r['source']=='silence']
            groups[style] = dict(n=len(speech), subtitle=sum(r['status']=='subtitle' for r in speech),
                median_ms=statistics.median(r['inference_ms'] for r in speech),
                silence=[r['status'] for r in silence])
        result[filename] = groups
    rows = read('paced.jsonl')
    probabilities = json.loads((S0 / 'clip_vad.json').read_text())
    samples = len(pcm_file(S0 / 'clip.wav'))//2
    reference = words(' '.join(c['english'] for c in read_srt(INPUT/'clip_gold_bilingual.srt')))
    result['paced'] = {}
    for policy in ['fixed_5000', 'pause_600_max_5000']:
        delivered = [r for r in rows if r.get('policy')==policy and r['type']=='delivered']
        dropped = [r for r in rows if r.get('policy')==policy and r['type']=='dropped']
        all_segments = sorted(delivered+dropped, key=lambda r:r['id'])
        expected = fixed(samples, 5000) if policy.startswith('fixed') else cuts(probabilities, samples)
        assert [(r['start_ms']*16, r['end_ms']*16) for r in all_segments] == [(r['start'],r['end']) for r in expected]
        assert all(r['completed_ms']>=r['started_ms']>=r['end_ms'] for r in delivered)
        hypothesis = words(' '.join(r.get('english') or '' for r in delivered if r['status']=='subtitle'))
        summary = next(r for r in rows if r.get('policy')==policy and r['type']=='policy_complete').copy()
        summary.update(subtitle=sum(r['status']=='subtitle' for r in delivered),
            english_wer=edit_distance(reference,hypothesis)/len(reference),
            dropped_ms=sum(r['end_ms']-r['start_ms'] for r in dropped),
            pause_cuts=sum(r['cut_reason']=='pause' for r in all_segments),
            peak_rss_kib=max(r['peak_rss_kib'] for r in delivered))
        for field in ['inference_ms', 'queue_wait_ms', 'cut_to_output_ms']:
            values = [r[field] for r in delivered if r['cut_reason']!='tail']
            summary[field] = dict(n=len(values), p50=statistics.median(values),p95=percentile(values,.95),max=max(values))
        pauses = [r['last_speech_to_output_ms'] for r in delivered if r['cut_reason']=='pause']
        summary['pause_last_speech_to_output_ms'] = dict(n=len(pauses),values=pauses,
            p50=statistics.median(pauses) if pauses else None)
        result['paced'][policy] = summary
    result['paired_pause_scheduling_proxy'] = []
    fixed_rows = [r for r in rows if r.get('policy')=='fixed_5000' and r['type']=='delivered']
    for pause in [r for r in rows if r.get('policy')=='pause_600_max_5000' and r['type']=='delivered' and r['cut_reason']=='pause']:
        anchor = pause['last_speech_ms']
        counterpart = next((r for r in fixed_rows if r['start_ms'] < anchor <= r['end_ms']), None)
        if counterpart:
            result['paired_pause_scheduling_proxy'].append(dict(anchor_ms=anchor,
                fixed_end_ms=counterpart['end_ms'], pause_end_ms=pause['end_ms'],
                fixed_status=counterpart['status'], pause_status=pause['status'],
                fixed_anchor_to_output_ms=counterpart['completed_ms']-anchor,
                pause_anchor_to_output_ms=pause['completed_ms']-anchor,
                saved_ms=counterpart['completed_ms']-pause['completed_ms']))
    result['latency_caveat'] = 'Decoder completion only. VAD last-speech anchors are not word alignment or semantic delivery; no screen first-display timing.'
    write_json(OUT/'summary.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['screening', 'choose', 'validation', 'paced', 'summarize'])
    args = parser.parse_args()
    {'screening': screening, 'choose': choose, 'validation': validation, 'paced': paced, 'summarize': summarize}[args.phase]()
