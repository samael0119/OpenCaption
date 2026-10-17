"""Pre-output AI-assisted reference audit; never rewrites publisher references."""
import json
from pathlib import Path
from v020_evidence11 import OUT, OLD, save, sha

NOTES = {
1860: dict(facts=['Governor office attributed statement','nineteen injured people were police'],
           key=['number19','injured subset, not all injured'], ambiguity=[], status='usable_with_frozen_rules'),
1870: dict(facts=['Scenes shown on pyramids','different pyramids illuminated'], key=[],
           ambiguity=['Scenes have no antecedent in this sentence; do not require inventing content'], status='usable_with_frozen_rules'),
1889: dict(facts=['It brought train and car','also many other transportation devices'], key=[],
           ambiguity=['It has no explicit antecedent; reference does not license inventing technology or a person'], status='usable_with_frozen_rules'),
1908: dict(facts=['This is an important distinguishing method','some verbs contrasted with objects'], key=[],
           ambiguity=['This has no antecedent; objects interpreted as grammatical objects in human Chinese, not independently established by isolated audio'], status='context_ambiguity'),
1941: dict(facts=['These couples may choose','an adoption plan concerning their baby'], key=['may is possibility, not certainty'],
           ambiguity=['Adoption direction not explicit in isolated sentence; do not require invented beneficiary or procedure'], status='usable_with_frozen_rules'),
1957: dict(facts=['He referred to rumors','called them political chatter and silliness'], key=['attribution, not narrator endorsement'],
           ambiguity=['He has no explicit identity; chatter translation admits paraphrases'], status='usable_with_frozen_rules'),
1972: dict(facts=['Many people do not think of them as dinosaurs','reason: feathers and ability to fly'], key=['negated belief attribution','both feathers and flight'],
           ambiguity=['Them has no antecedent; Chinese reference could be misread as asserting not dinosaurs rather than reporting belief'], status='usable_with_frozen_rules'),
1978: dict(facts=['Springboks affected','a five-match losing streak ended'], key=['five matches','ended streak, not ended with streak'],
           ambiguity=['Publisher Chinese says ended with five losses; contradicts English termination of losing streak'], status='reference_conflict_do_not_score_against_chinese'),
}


def main():
    q=json.loads((OUT/'qualification.json').read_text())
    ids={x['id'] for x in q['selected']}
    if ids != set(NOTES): raise RuntimeError('Audit does not match frozen selected IDs')
    entries=[]
    for x in q['selected']:
        entries.append(dict(id=x['id'], reference_en=x['reference_en'], reference_zh=x['reference_zh'],
            reference_en_sha256=__import__('hashlib').sha256(x['reference_en'].encode()).hexdigest(),
            reference_zh_sha256=__import__('hashlib').sha256(x['reference_zh'].encode()).hexdigest(), **NOTES[x['id']]))
    manifest=json.loads((OUT/'manifest.json').read_text())
    unchanged=all(sha(p)==h for p,h in manifest['inputs'].items())
    snapshot=json.loads(Path('evaluation/results/v020-round2/scene-denial/source_snapshot.json').read_text())
    files=snapshot['files']
    if isinstance(files,list): raise RuntimeError('Unexpected source snapshot shape')
    product_unchanged=all(sha(p)==h for p,h in files.items())
    assert unchanged and product_unchanged
    save('reference_audit.json',dict(audit_type='AI-assisted pre-output review, not independent human adjudication',
        original_references_unchanged=True, no_reference_rewrite=True, selected_denominator=8,
        usable_with_rules=6, context_ambiguity=1, explicit_reference_conflict=1, entries=entries,
        conflict_policy='Retain all8; do not compute model accuracy or silently drop1978. Any future scoring must freeze disputed/unknown handling and show all8 denominator separately.',
        input_integrity_unchanged=unchanged, product_files_unchanged=len(files) if product_unchanged else False,
        model_requests=0, network_requests=0))
    save('validation.json',dict(unit_tests=10, unit_test_failures=0,
        test_evidence='Observed unittest exit0, Ran10 tests,0.005s; explicit512MiB/swap0/60s systemd scope',
        scan_exit=0, scan_timeout_seconds=120, scan_memory_max='512MiB', scan_swap_max=0,
        selected_audio_bytes=q['new_audio_bytes'], audio_limit_bytes=64*1024*1024,
        original_inputs_unchanged=unchanged, product_files_unchanged=len(files),
        full_archive_integrity_verified=False, expected_prefix_truncation=True,
        inference_model_not_loaded=True, runtime_memory_peak_not_measured=True))
    save('result_hashes.json',{str(p):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='result_hashes.json'})
    print(json.dumps(dict(cases=8, usable_with_rules=6, ambiguous=1, conflict=1,
                          original_inputs_unchanged=unchanged, product_files_unchanged=len(files))))


if __name__ == '__main__':main()
