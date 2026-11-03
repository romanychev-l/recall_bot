"""Extract standard English inflections from Kaikki/Wiktionary for chat practice.

python -m data.build_word_forms --kaikki kaikki.org-dictionary-English.jsonl.gz
Only actual inflections are imported: prefixes/derivations are never stripped.
"""
from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path

from data.build_dictionary import iter_kaikki

INFLECTIONS = {'plural', 'comparative', 'superlative', 'present', 'past', 'participle'}
EXCLUDED = {'archaic', 'obsolete', 'nonstandard', 'rare', 'dialectal', 'alternative',
            'humorous', 'dated', 'pronunciation-spelling', 'error-unrecognized-form'}
CONTENT_POS = {'noun', 'verb', 'adj', 'adv'}
FORM = re.compile(r"[a-z]+(?:['-][a-z]+)*(?: [a-z]+(?:['-][a-z]+)*){0,2}")


def names_only(dictionary: Path) -> set[str]:
    senses = dictionary.with_name(dictionary.stem + '_senses.csv')
    metadata = defaultdict(set)
    if senses.exists():
        with senses.open(encoding='utf-8', newline='') as source:
            for row in csv.DictReader(source):
                metadata[row['english']].update(row['parts_of_speech'].split('|'))
    return {word for word, parts in metadata.items() if 'name' in parts and not parts & CONTENT_POS}


def build_forms(dictionary: Path, kaikki: Path, output: Path) -> None:
    with dictionary.open(encoding='utf-8', newline='') as source:
        wanted = {r['english'] for r in csv.DictReader(source)}
    forms = set()
    excluded_names = names_only(dictionary)
    for entry in iter_kaikki(kaikki):
        # Proper names must not add unrelated forms to a common noun/verb.
        english = entry.get('word') or ''
        pos = entry.get('pos')
        if english not in wanted or english in excluded_names or pos not in CONTENT_POS:
            continue
        if not any(not set(sense.get('tags', [])) & EXCLUDED for sense in entry.get('senses', [])):
            continue
        for item in entry.get('forms', []):
            tags = set(item.get('tags', []))
            form = ' '.join((item.get('form') or '').lower().split())
            if tags & INFLECTIONS and not tags & EXCLUDED and FORM.fullmatch(form) and form != english:
                forms.add((form, english, pos))
    with output.open('w', encoding='utf-8', newline='') as target:
        writer = csv.writer(target, lineterminator='\n')
        writer.writerow(['form', 'english', 'pos'])
        writer.writerows(sorted(forms))
    print(f'Wrote {len(forms)} validated inflections to {output}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dictionary', type=Path, default=Path('data/dictionary.csv'))
    parser.add_argument('--kaikki', type=Path, required=True)
    parser.add_argument('--out', type=Path, default=Path('data/dictionary_forms.csv'))
    args = parser.parse_args()
    build_forms(args.dictionary, args.kaikki, args.out)
