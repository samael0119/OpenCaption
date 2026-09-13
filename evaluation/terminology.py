"""Deterministic correction using the app's curated corpus metadata."""
import json
import re
from pathlib import Path


def normalize(text):
    return re.sub(r"[^a-z0-9']+", ' ', text.lower()).strip()


def contains(text, phrase):
    return bool(normalize(phrase)) and f' {normalize(phrase)} ' in f' {normalize(text)} '


class Terminology:
    def __init__(self, root=None):
        root = root or Path(__file__).resolve().parents[1]
        manifest = json.loads((root / 'assets/corpora/manifest.json').read_text())
        self.terms = []
        for pack in manifest['packs']:
            if pack.get('enabled') is not False:
                self.terms.extend(json.loads((root / pack['asset']).read_text())['terms'])

    def correct(self, english, chinese):
        replacements = {}
        for term in self.terms:
            if not any(contains(english, s) for s in term.get('correction_sources', [term['english']])):
                continue
            if any(contains(english, s) for s in term.get('correction_exclude', [])):
                continue
            for wrong in term.get('wrong_targets', []):
                if wrong and wrong not in term['chinese']:
                    replacements.setdefault(wrong, set()).add(term['chinese'])
        keys = sorted((k for k, v in replacements.items() if len(v) == 1), key=lambda k: (-len(k), k))
        if not keys:
            return chinese
        return re.sub('|'.join(map(re.escape, keys)), lambda m: next(iter(replacements[m[0]])), chinese)
