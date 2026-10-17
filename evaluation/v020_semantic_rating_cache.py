"""Reuse a frozen semantic judgment for identical case, reference and raw bytes.

Human/AI provenance remains unchanged. Conflicts require review, never a higher
score chosen after a candidate. This is an audit, not automatic semantic gold.
"""
import hashlib


def raw_digest(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def frozen_judgment(case_id, raw, units, records):
    digest = raw_digest(raw)
    matching = []
    for record in records:
        if record['case_id'] != case_id or record['raw_sha256'] != digest:
            continue
        if raw_digest(record['actual_raw']) != digest:
            raise ValueError('Stored raw SHA mismatch')
        if record['semantic_units'] != units:
            raise ValueError('Reference changed for identical case/raw')
        matching.append((tuple(record['english_ratings']),
                         tuple(record['chinese_ratings'])))
    if not matching:
        return None
    if len(set(matching)) != 1:
        raise ValueError('Conflicting frozen judgments; do not select a score')
    english, chinese = matching[0]
    return {'en': list(english), 'zh': list(chinese),
            'provenance': 'exact_case_units_raw_SHA_frozen_judgment_reuse'}


def preserved_count(ratings):
    return sum(value == 'preserved' for value in ratings)
