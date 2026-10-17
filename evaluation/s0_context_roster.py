"""Follow-up: context capacity versus actual prompt length, and roster evidence.

Temporal/alias changes below are an evaluation prototype. A match-specific
fixture is an oracle control, never an automatically inferred roster.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import resource
import statistics
import time

from e2e_protocol import PROMPT, parse_output
from gemma_replay import LiteRtRuntime, response_text, write_chunk
from s0_probe import OUT as S0, ROOT, SYSTEM, SceneIndex, pcm_file, write_json

OUT = S0 / "context_roster"


class IdentityIndex:
    """Separate immutable spelling, weak aliases and dated snapshot relations."""
    def __init__(self):
        pack = json.loads((ROOT / "assets/corpora/cs2_zh_broadcast_live_entities_v0.2.json").read_text())
        self.snapshot = pack['provenance']['snapshot']
        self.players = {t['english']: t for t in pack['terms'] if t['category'] == 'player'}
        self.aliases = {}
        self.weak = {'bit', 'wonderful', 'frozen'}
        for canonical, term in self.players.items():
            for alias in {canonical, *term.get('aliases', [])}:
                self.aliases.setdefault(alias.lower(), set()).add(canonical)

    def mentions(self, text):
        hits = []
        for alias, candidates in self.aliases.items():
            for match in re.finditer(r'(?<![A-Za-z0-9])' + re.escape(alias) + r'(?![A-Za-z0-9])', text, re.I):
                hits.append(dict(text=match[0], start=match.start(), end=match.end(),
                    canonical=sorted(candidates), strength='weak' if alias in self.weak else 'exact_alias'))
        return hits

    def normalize(self, text):
        # No phonetic/guessing replacements: only unique, non-weak curated aliases.
        hits = [h for h in self.mentions(text) if h['strength'] != 'weak' and len(h['canonical']) == 1]
        for hit in sorted(hits, key=lambda h: h['start'], reverse=True):
            text = text[:hit['start']] + hit['canonical'][0] + text[hit['end']:]
        return text

    def affiliation(self, canonical, observed_date=None, match_fixture=None):
        if match_fixture and canonical in match_fixture:
            return dict(team=match_fixture[canonical], state='match_specific_reference',
                        source='user-supplied clip metadata; oracle only')
        if canonical not in self.players:
            return dict(team=None, state='unknown_player')
        if observed_date and date.fromisoformat(observed_date) < date.fromisoformat(self.snapshot):
            return dict(team=None, state='unknown_historical_affiliation', snapshot=self.snapshot)
        team = self.players[canonical]['context'].removeprefix('战队：')
        return dict(team=team, state='snapshot_candidate_only', snapshot=self.snapshot)


def roster_probe():
    OUT.mkdir(parents=True, exist_ok=True)
    index = IdentityIndex()
    samples = ['a little bit around that door', 'a wonderful shot',
               'Shiro holds the angle', 'b1t finishes the job', 'frozen makes it a one-round game']
    fixtures = []
    for text in samples:
        fixtures.append(dict(text=text, old_candidates=SceneIndex().observe(text)['teams'],
                             improved_mentions=index.mentions(text), normalized=index.normalize(text)))
    result = dict(snapshot=index.snapshot, scope='dictionary prototype, not acoustic/translation quality',
        alias_probes=fixtures, temporal_probes=dict(
            old_karrigan=SceneIndex().observe('karrigan')['teams'],
            unknown_date=index.affiliation('karrigan'),
            historical=index.affiliation('karrigan', '2025-12-01'),
            historical_oracle=index.affiliation('karrigan', match_fixture={'karrigan': 'FaZe'}),
            missing_player=index.affiliation('broky')))
    write_json(OUT / 'roster_probe.json', result)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def preceding_text(source, start):
    path = S0 / ('inference.jsonl' if source == 'clip' else 'supplement.jsonl')
    group = 'fixed_5000' if source == 'clip' else 'historical_match'
    rows = [json.loads(s) for s in path.read_text().splitlines()]
    completed = [r for r in rows if r.get('group') == group and r['end_ms'] <= start
                 and r.get('status') == 'subtitle']
    return ' '.join(r['english'] for r in completed[-2:])[:320]


def hint_for(style, source, start):
    if style == 'control':
        return ''
    if style == 'identity':
        return ('Name spellings: sh1ro (shiro), xertioN (xertion).' if source == 'clip'
                else 'Name spellings: b1t, frozen, jcobbb.')
    if style == 'scene_glossary':
        return ('Scene: Spirit vs MOUZ on Dust II. Scout=鸟狙; save=保枪. Names: sh1ro, xertioN.'
                if source == 'clip' else
                'Scene: NAVI vs FaZe on Nuke. Heaven=天堂; Hell=地狱; Vent=通风管道. Names: b1t, frozen, jcobbb.')
    if style == 'brief_history':
        return 'Earlier transcript (may be inaccurate, do not repeat): ' + preceding_text(source, start)
    if style == 'stress':
        index = SceneIndex()
        glossary = '; '.join(f"{t['english']}={t['chinese']}" for t in index.maps['Nuke'][:12])
        return 'Nuke. ' + glossary + '; Previous transcript: ' + 'A player moves outside and waits. ' * 50
    raise ValueError(style)


def run(context):
    OUT.mkdir(parents=True, exist_ok=True)
    args = argparse.Namespace(model=Path('/home/hyh/Tools/litert/models/gemma-4-E2B-it.litertlm'),
        threads=4, max_new_tokens=128, hints='', task='bilingual', task_profile='baseline',
        system_profile='baseline', cache_mode='memory', speculative_decoding='true',
        max_context_tokens=context)
    started = time.monotonic()
    runtime = LiteRtRuntime(args)
    api = runtime.api
    init_ms = round((time.monotonic() - started) * 1000)
    chunk = OUT / 'chunk.wav'
    write_chunk(chunk, pcm_file(S0 / 'clip.wav')[:160000])
    runtime.system_message = SYSTEM
    runtime.infer(chunk)
    cases = [('clip', 10000), ('clip', 25000), ('clip_match_demo3', 10000)]
    styles = ['control', 'identity', 'scene_glossary', 'brief_history']
    jobs = [(repeat, source, start, style) for repeat in (1, 2)
            for source, start in cases for style in (styles if repeat == 1 else list(reversed(styles)))]
    jobs.append((1, 'clip_match_demo3', 10000, 'stress'))
    with args.model.open('rb') as model_file:
        sha = hashlib.file_digest(model_file, 'sha256').hexdigest()
    metadata = dict(type='metadata', context=context, model_sha256=sha, init_ms=init_ms,
                    warmup=1, jobs=len(jobs), repeat=2, backend='CPU', threads=4,
                    mtp=True, max_output=128, cache='memory', scene_hints='oracle controls')
    try:
        with (OUT / f'context_{context}.jsonl').open('w') as report:
            report.write(json.dumps(metadata) + '\n')
            for number, (repeat, source, start, style) in enumerate(jobs, 1):
                write_chunk(chunk, pcm_file(S0 / (source + '.wav'))[start * 32:(start + 5000) * 32])
                hint = hint_for(style, source, start)
                system = SYSTEM + (' ' + hint if hint else '')
                row = dict(type='window', repeat=repeat, source=source, start_ms=start,
                    end_ms=start + 5000, style=style, context=context, hint_chars=len(hint),
                    text_tokens=len(runtime.engine.tokenize(system + PROMPT)))
                began = time.monotonic()
                try:
                    with runtime.engine.create_conversation(system_message=system,
                         thinking_config=api.ThinkingConfig(False, 0),
                         sampler_config=api.SamplerConfig(top_k=1, top_p=1.0, temperature=0.0),
                         max_output_tokens=128) as conversation:
                        response = conversation.send_message(
                            api.Contents.of(PROMPT, api.Content.AudioFile(str(chunk.resolve()))),
                            max_output_tokens=128, thinking_config=api.ThinkingConfig(False, 0))
                        row['raw'] = response_text(response)
                        row.update(asdict(parse_output(row['raw'])))
                        row['conversation_tokens'] = conversation.token_count
                        row['context_capacity_hit'] = row['conversation_tokens'] >= context
                        row['normalized_english'] = IdentityIndex().normalize(row.get('english') or '')
                        row['output_tokens'] = len(runtime.engine.tokenize(row['raw']))
                except Exception as error:
                    row.update(status='exception', error=str(error))
                row['inference_ms'] = round((time.monotonic() - began) * 1000)
                row['peak_rss_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                report.write(json.dumps(row, ensure_ascii=False) + '\n')
                report.flush()
                print(f"{context} {number}/{len(jobs)} {source}@{start} {style} {row['inference_ms']}ms {row['status']}", flush=True)
            report.write(json.dumps(dict(type='complete', completed=len(jobs))) + '\n')
    finally:
        runtime.close()


def summarize():
    summary = {}
    for context in (768, 1024):
        rows = [json.loads(s) for s in (OUT / f'context_{context}.jsonl').read_text().splitlines()]
        if rows[-1].get('type') != 'complete':
            raise ValueError('Incomplete context experiment')
        groups = {}
        for style in ['control', 'identity', 'scene_glossary', 'brief_history', 'stress']:
            items = [r for r in rows if r.get('style') == style]
            groups[style] = dict(count=len(items), subtitle=sum(r.get('status') == 'subtitle' for r in items),
                median_ms=statistics.median(r['inference_ms'] for r in items),
                max_text_tokens=max(r['text_tokens'] for r in items),
                max_conversation_tokens=max(r.get('conversation_tokens', 0) for r in items),
                peak_rss_kib=max(r['peak_rss_kib'] for r in items),
                normalized_changed=sum(r.get('english') != r.get('normalized_english')
                                       for r in items if r.get('status') == 'subtitle'),
                context_capacity_hits=sum(r.get('conversation_tokens', 0) >= context for r in items))
        summary[str(context)] = dict(metadata=rows[0], groups=groups)
    write_json(OUT / 'summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=['run', 'roster', 'summarize'])
    parser.add_argument('--context', type=int, choices=[768, 1024], default=768)
    args = parser.parse_args()
    if args.phase == 'run':
        run(args.context)
    elif args.phase == 'roster':
        roster_probe()
    else:
        summarize()
