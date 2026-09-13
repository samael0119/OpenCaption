"""Relative English ASR score against the user's non-gold, untimed transcript."""
import argparse
import json
import re
from pathlib import Path

from protocol_candidate import parse_candidate

ENTITIES = ("donk", "sh1ro", "tn1r", "zont1x", "torzsi", "xertion", "spirit", "mouz", "dust2")


def words(text):
    return re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text.lower())


def reference_english(path):
    lines = [line.strip() for line in Path(path).read_text().splitlines()]
    try:
        lines = lines[lines.index("翻译对照:") + 1:]
    except ValueError:
        pass
    nonempty = [line for line in lines if line and set(line) != {"-"}]
    return " ".join(nonempty[0::2])


def hypothesis(path):
    output = []
    for line in Path(path).read_text().splitlines():
        row = json.loads(line)
        if row.get("type") != "window" or not row.get("raw"):
            continue
        if row.get("task") == "english":
            if row.get("status") == "transcription":
                output.append(re.sub(r"^\s*(?:English|EN|Transcription)\s*[:：]\s*", "", row["raw"], flags=re.I))
            continue
        parsed = parse_candidate(row["raw"])
        if parsed.status == "subtitle":
            output.append(parsed.english)
    return " ".join(output)


def edit_distance(a, b):
    previous = list(range(len(b) + 1))
    for i, left in enumerate(a, 1):
        current = [i]
        for j, right in enumerate(b, 1):
            current.append(min(current[-1] + 1, previous[j] + 1,
                               previous[j-1] + (left != right)))
        previous = current
    return previous[-1]


def lcs_length(a, b):
    previous = [0] * (len(b) + 1)
    for left in a:
        current = [0]
        for j, right in enumerate(b, 1):
            current.append(previous[j-1] + 1 if left == right else max(previous[j], current[-1]))
        previous = current
    return previous[-1]


def score(reference, output):
    ref, hyp = words(reference), words(output)
    ref_entities = {entity: ref.count(entity) for entity in ENTITIES if ref.count(entity)}
    hyp_entities = {entity: hyp.count(entity) for entity in ref_entities}
    matched = {entity: min(count, hyp_entities[entity]) for entity, count in ref_entities.items()}
    return {
        "reference_words": len(ref), "hypothesis_words": len(hyp),
        "wer": round(edit_distance(ref, hyp) / len(ref), 3) if ref else None,
        "ordered_word_coverage": round(lcs_length(ref, hyp) / len(ref), 3) if ref else None,
        "entity_recall": round(sum(matched.values()) / sum(ref_entities.values()), 3) if ref_entities else None,
        "reference_entity_counts": ref_entities, "matched_entity_counts": matched,
        "caveat": "relative score against untimed, non-gold user transcript; bilingual mode scores delivered English (includes parser omissions); entity_recall is unaligned capped-count proxy, not entity accuracy",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference")
    parser.add_argument("logs", nargs="+")
    args = parser.parse_args()
    reference = reference_english(args.reference)
    for log in args.logs:
        print(json.dumps({"file": log, **score(reference, hypothesis(log))}, ensure_ascii=False))
