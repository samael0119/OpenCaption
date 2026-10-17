"""One-shot audit of actual G1 outputs and transparent AI-assisted unit ratings."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics

from score_reference import words, edit_distance

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'evaluation/results/v020-convergence'
# Ratings follow the original 18 units without rewriting the references.
P, O, C, U = 'preserved', 'omitted', 'contradicted', 'uncertain'
RATINGS = {
    1700: {'en': [O, P, O], 'zh': [O, U, O], 'text': [U, P, P],
           'reason': 'Both audio arms replace thinner with dinner. Chinese 吃更厚 is unresolved rather than a correct thickness relation. Text restores thin/thick; 马里亚 technical referent is uncertain.'},
    1750: {'en': [P, P, O], 'zh': [P, P, O], 'text': [P, P, P],
           'reason': 'Audio feathers and birds loses the feathers-in-birds relation; Chinese faithfully propagates that loss. Text explicitly says 鸟类羽毛.'},
    1776: {'en': [O, P, P, C], 'zh': [O, O, P, C], 'text': [U, U, P, P],
           'reason': 'Audio loses through-the-night and substitutes LaBread/Lenna for Dunlap. Chinese keeps numbers but omits copies being made. Text keeps the exact name, but 夜间 and 在150到200之间...copies do not clearly preserve one-night/count semantics.'},
    1778: {'en': [P, P], 'zh': [P, P], 'text': [P, P],
           'reason': 'All three arms preserve TV reports and factory white smoke; no CS2 plant insertion.'},
    1791: {'en': [O, P, O], 'zh': [O, P, O], 'text': [C, P, P],
           'reason': 'Both audio arms omit prohibition; marking/scratching graffiti into structures remains. Text restores negation but turns a physical site into 网站; not a full correct translation.'},
    1792: {'en': [P, P, P], 'zh': [P, P, P], 'text': [P, P, P],
           'reason': 'Chemical pH, making an indicator and red cabbage juice are preserved. Text has untranslated cabbage but 紫甘蓝 explicitly preserves its referent; score semantic meaning, not exact spelling.'},
}


def main():
    manifest = json.loads((OUT / 'g1_manifest.json').read_text())
    data = (OUT / 'g1_requests.jsonl').read_bytes()
    rows = [json.loads(line) for line in data.decode().splitlines()]
    actual = [r for r in rows if r['type'] == 'request']
    expected = [(r['case_id'], r['mode'], r['modality']) for r in manifest['order']]
    if rows[-1]['type'] != 'complete' or len(actual) != 18 or [
            (r['case_id'], r['mode'], r['modality']) for r in actual] != expected:
        raise RuntimeError('Incomplete/reordered/duplicate results; refuse summary')
    cases = {c['id']: c for c in manifest['cases']}
    annotated = []
    groups = {}
    for mode in ['baseline', 'domain', 'text_reference']:
        selected = [r for r in actual if r['mode'] == mode]
        en, zh, strict = Counter(), Counter(), 0
        categories = Counter()
        for row in selected:
            rating = RATINGS[row['case_id']]
            if mode == 'text_reference':
                targets = rating['text']
                zh.update(targets)
                strict += all(x == P for x in targets)
            else:
                targets = rating['zh']
                en.update(rating['en']); zh.update(targets)
                strict += row['status'] == 'subtitle' and all(x == P for x in rating['en'] + targets)
                for english, chinese in zip(rating['en'], targets):
                    if chinese == P:
                        continue
                    categories['unknown' if chinese == U else 'shared_upstream_loss' if english != P else 'chinese_loss_with_preserved_english'] += 1
            annotated.append(dict(index=row['index'], case_id=row['case_id'], mode=mode,
                raw_sha256=hashlib.sha256(row['raw'].encode()).hexdigest(),
                english_ratings=rating['en'] if mode != 'text_reference' else None,
                chinese_ratings=targets, reason=rating['reason'],
                semantic_units=cases[row['case_id']]['semantic_units'], actual_raw=row['raw']))
        stats = dict(cases=6, english_unit_ratings=dict(en), chinese_unit_ratings=dict(zh),
                     semantic_unit_denominator=18, strict_correct_cases=strict,
                     median_decoder_ms=statistics.median(r['inference_ms'] for r in selected),
                     decoder_ms=[r['inference_ms'] for r in selected], error_localization=dict(categories))
        if mode != 'text_reference':
            total = sum(len(words(cases[r['case_id']]['reference_en'])) for r in selected)
            errors = sum(edit_distance(words(cases[r['case_id']]['reference_en']), words(r['english'])) for r in selected)
            stats.update(literal_reference_words=total, literal_word_errors=errors, literal_wer=errors/total,
                         statuses=dict(Counter(r['status'] for r in selected)),
                         missing_prohibition_cases=1, wrong_specific_name_cases=1,
                         unsupported_cs2_entities=0)
        groups[mode] = stats
    summary = dict(complete=True, result_sha256=hashlib.sha256(data).hexdigest(),
        manifest_sha256=hashlib.sha256((OUT/'g1_manifest.json').read_bytes()).hexdigest(),
        reviewer='AI-assisted; independent human review NOT performed',
        groups=groups, paired_audio_complete_case_gains=0, paired_audio_complete_case_losses=0,
        no_hint_semantic_unit_errors=9, shared_upstream_losses=7,
        downstream_losses_with_preserved_english=1, unresolved_losses=1,
        top_two_localization_share=8/9, localization_is_causal_proof=False,
        optimization_candidate_tested=False, verified_optimization_gain=False,
        official_acceptance_passed=False, sample_count=6, pretraining_contamination='unknown',
        timing='decoder only; cold first audio included; no n6 P95, no audio-vs-text causal speed comparison',
        resource_end=rows[-1]['resources'], peak_model_rss_kib=max(r['peak_rss_kib'] for r in actual))
    for filename, value in [('g1_semantic_review.json', annotated), ('g1_summary.json', summary)]:
        with (OUT/filename).open('x') as stream:
            stream.write(json.dumps(value, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
