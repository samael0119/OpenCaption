"""Map evidence recovery prototype; dictionary/rule diagnostics, not truth.

Does not infer team membership from current rosters. Cross-map aliases and
common English terms remain weak; only location phrases add point evidence.
"""
from collections import defaultdict, deque
import json
import re

from s0_probe import OUT as S0, SceneIndex, write_json

OUT = S0 / 'protocol_live'


class MapEvidence:
    def __init__(self, ttl_ms=60000, relations=True):
        index = SceneIndex()
        self.maps = defaultdict(set)
        self.point_ids = defaultdict(set)
        self.names = {}
        self.weak = {'outside', 'heaven', 'hell', 'headshot', 'ramp', 'mid', 'main',
                     'ct', 'a', 'b', 'site', 'a site', 'b site', 'upper', 'lower', 'red', 'long'}
        for alias, terms in index.aliases.items():
            for term in terms:
                if term.get('category') == 'map_callout':
                    self.maps[alias].add(term['context'].removeprefix('地图：'))
                    self.point_ids[alias].add(term['id'])
                elif term.get('id', '').startswith('live-map-'):
                    self.names[alias] = term['english']
        self.ttl = ttl_ms
        self.evidence = deque(maxlen=12)
        self.seen = deque(maxlen=256)
        self.epoch = 0
        self.relations = relations
        self.now_ms = 0
        self.last_event_end = -1

    def reset(self):
        self.evidence.clear(); self.seen.clear(); self.epoch += 1
        self.now_ms = 0
        self.last_event_end = -1

    @staticmethod
    def negated(text, position):
        clause = re.split(r'[.,;!?]|\bbut\b',text[:position],flags=re.I)[-1]
        return bool(re.search(r"\b(?:not|never|isn't|aren't|wasn't|weren't|don't|doesn't|no longer)\b(?:\s+\w+){0,2}\s*$",clause,re.I))

    def update(self, text, end_ms, segment_id, hinted_aliases=(), epoch=None):
        if epoch is not None and epoch != self.epoch:
            return self.view(self.now_ms)
        if segment_id in self.seen or end_ms<=self.last_event_end:
            return self.view(self.now_ms)
        self.last_event_end=end_ms
        self.seen.append(segment_id)
        if re.search(r'\b(last map|previous map|yesterday|used to|last year)\b', text, re.I):
            return self.view(end_ms)
        hinted = {s.lower() for s in hinted_aliases}
        hinted_ids = set().union(*(self.point_ids[a] for a in hinted)) if hinted else set()
        points = defaultdict(set)
        explicit = set()
        denied = set()
        for alias, name in self.names.items():
            if alias in hinted:
                continue
            for match in re.finditer(r'\b(?:on|current map is|playing)\s+' + re.escape(alias) + r'\b', text, re.I):
                if self.relations and self.negated(text,match.start()):
                    denied.add(name)
                else:
                    explicit.add(name)
        if denied:
            # An explicit current-map denial releases the previous hypothesis.
            # Any fresh positive declaration in the same segment is re-added.
            self.evidence.clear()
        for alias, maps in self.maps.items():
            if alias in self.weak or alias in hinted or (self.relations and self.point_ids[alias]&hinted_ids) or len(alias) <= 2:
                continue
            for match in re.finditer(r'\b(?:through|towards|into|at|in|up|down|on|from|holding|taking)\s+(?:the\s+)?'
                         + re.escape(alias) + r'\b', text, re.I):
                if self.relations and self.negated(text,match.start()):
                    continue
                for name in maps-denied:
                    points[name].add(alias)
        if points or explicit:
            self.evidence.append(dict(end_ms=end_ms, id=segment_id,
                explicit=explicit, points=dict(points)))
        return self.view(end_ms)

    def view(self, now_ms):
        self.now_ms=max(self.now_ms,now_ms)
        now_ms=self.now_ms
        self.evidence = deque([e for e in self.evidence if 0 <= now_ms - e['end_ms'] < self.ttl], maxlen=12)
        score, entities, segments = defaultdict(float), defaultdict(set), defaultdict(set)
        point_groups = {}
        direct = set()
        for e in self.evidence:
            for name in e['explicit']:
                score[name] += 4
                direct.add(name); segments[name].add(e['id'])
            for name, aliases in e['points'].items():
                entities[name].update(aliases)
                segments[name].add(e['id'])
                for alias in aliases:
                    # Vent/vents and other aliases of the same relation are one
                    # fact, even when their spelling differs between segments.
                    key = tuple(sorted(self.point_ids[alias]))
                    item = point_groups.setdefault(key, dict(maps=set(self.maps[alias]), ids=set()))
                    item['ids'].add(e['id'])
        if self.relations:
            for group in point_groups.values():
                for name in group['maps']:
                    score[name] += 1/len(group['maps'])
        else:
            for name, aliases in entities.items():
                score[name] += sum(1 / len(self.maps[a]) for a in aliases)
        ranked = sorted(score.items(), key=lambda s: (-s[1], s[0]))
        if not ranked:
            return dict(status='unknown', map=None, candidates={}, epoch=self.epoch)
        top, strength = ranked[0]
        margin = strength - (ranked[1][1] if len(ranked) > 1 else 0)
        concepts = sum(top in g['maps'] for g in point_groups.values()) if self.relations else len(entities[top])
        enough = top in direct or (concepts >= 2 and len(segments[top]) >= 2)
        confirmed = enough and strength >= 2 and margin >= 2
        # Stronger relational evidence: two distinct location concepts in
        # separate segments, with an unambiguous joint map and a unique anchor.
        # This preserves all map relations instead of treating Vent as Nuke.
        joint = set.intersection(*(g['maps'] for g in point_groups.values())) if point_groups else set()
        unique_anchors = set().union(*(g['maps'] for g in point_groups.values() if len(g['maps'])==1))
        relational = (len(point_groups)>=2 and len(joint)==1 and bool(unique_anchors)
                      and len(set().union(*(g['ids'] for g in point_groups.values())))>=2)
        if self.relations and len(unique_anchors)>1 and not direct:
            confirmed = False
        if self.relations and relational and not direct:
            top = next(iter(joint))
            confirmed = True
        result = dict(status='supported' if confirmed else 'candidate_or_conflict',
                    map=top if confirmed else None, candidates=dict(ranked), epoch=self.epoch)
        if self.relations:
            result['support']='relation_intersection' if relational and not direct and confirmed else 'weighted_evidence'
        return result


def diagnostics(relations=True):
    OUT.mkdir(parents=True, exist_ok=True)
    scenarios = {
        'wrong_then_switch': [(0, 'on Nuke'), (5000, 'on Mirage'), (10000, 'on Mirage')],
        'point_accumulation': [(0, 'through Secret and holding Silo'), (5000, 'holding Hut')],
        'historical_mention': [(0, 'on Nuke'), (5000, 'last map we were on Mirage')],
        'shared_words': [(0, 'headshot at heaven'), (5000, 'ramp and a little bit')],
    }
    output = {}
    for name, rows in scenarios.items():
        state = MapEvidence(relations=relations)
        output[name] = [dict(time=ms, text=text, result=state.update(text, ms, i))
                        for i, (ms, text) in enumerate(rows)]
    timelines = {}
    for source, path, group in [('clip', S0 / 'inference.jsonl', 'fixed_5000'),
                               ('historical_nuke', S0 / 'supplement.jsonl', 'historical_match')]:
        state = MapEvidence(relations=relations)
        rows = [json.loads(s) for s in path.read_text().splitlines()]
        timelines[source] = [dict(end_ms=r['end_ms'], state=state.update(r['english'], r['end_ms'], r['start_ms']))
            for r in rows if r.get('group') == group and r.get('status') == 'subtitle']
    filename = 'scene_recovery_relations.json' if relations else 'scene_recovery.json'
    write_json(OUT / filename, dict(synthetic=output, model_text=timelines,
        caveat='Rules were developed using these clips; no independent accuracy claim'))
    print(json.dumps(dict(synthetic=output, model_text=timelines), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    diagnostics()
