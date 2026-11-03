"""Attach one or two usage examples to every dictionary entry, with provenance.

Run with local Tatoeba exports and the Kaikki/Wiktionary dump. No runtime network
or model calls are needed. Authored examples override corpus candidates.
"""
from __future__ import annotations

import argparse
import bz2
import csv
import re
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

from data.build_dictionary import iter_kaikki

TOKEN = re.compile(r"[A-Za-z]+(?:['’-][A-Za-z]+)*")
SOURCE_FIELDS = ['english', 'example', 'source', 'source_url', 'author', 'license']
ROUGH_LANGUAGE = {'fuck', 'fucking', 'fucked', 'shit', 'shitty', 'bitch', 'bastard',
                  'cunt', 'asshole', 'nigger', 'faggot', 'cock', 'dick', 'pussy'}


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding='utf-8', newline='') as source:
        return list(csv.DictReader(source))


@lru_cache(maxsize=30000)
def word_pattern(word: str) -> re.Pattern:
    return re.compile(r'(?<![\w-])' + re.escape(word) + r'(?![\w-])', re.I)


def contains_word(text: str, word: str) -> bool:
    return word_pattern(word).search(text) is not None


def sentence_score(text: str, ranks: dict[str, int]) -> float:
    tokens = TOKEN.findall(text.lower())
    rough_context = 20000 * len(set(tokens) & ROUGH_LANGUAGE)
    return rough_context + abs(len(tokens) - 9) * 130 + sum(ranks.get(t, 20000) for t in tokens) / max(1, len(tokens))


def add_candidate(candidates: dict, word: str, text: str, score: float, **source) -> None:
    pool = candidates[word]
    if len(pool) == 8 and score > pool[-1][0]:
        return
    text = ' '.join(text.split())
    if not contains_word(text, word):
        return
    if any(item['example'] == text for _, item in pool):
        return
    pool.append((score, dict(english=word, example=text, **source)))
    pool.sort(key=lambda item: (item[0], item[1]['example']))
    del pool[8:]


def collect_tatoeba(path: Path, candidates: dict, ranks: dict[str, int], *, cc0: bool) -> None:
    with bz2.open(path, 'rt', encoding='utf-8') as source:
        for line in source:
            columns = line.rstrip('\n').split('\t')
            sid, language, text = columns[:3]
            if language != 'eng' or not 12 <= len(text) <= 220 or text[-1:] not in '.?!':
                continue
            if any(c in text for c in ['"', '…', '[', ']', '{', '}', '<', '>', 'http']):
                continue
            tokens = TOKEN.findall(text.lower())
            if not 3 <= len(tokens) <= 28:
                continue
            score = sentence_score(text, ranks) + (0 if cc0 else 200)
            for word in set(tokens) & ranks.keys():
                add_candidate(candidates, word, text, score,
                              source='Tatoeba', source_url=f'https://tatoeba.org/en/sentences/show/{sid}',
                              author='' if cc0 else ('Tatoeba contributors' if columns[3] == '\\N' else columns[3]),
                              license='CC0-1.0' if cc0 else 'CC-BY-2.0-FR')


def collect_kaikki(path: Path, candidates: dict, ranks: dict[str, int], parts: dict[str, str]) -> None:
    from urllib.parse import quote
    for entry in iter_kaikki(path):
        word = (entry.get('word') or '').lower()
        if word not in ranks:
            continue
        for sense in entry.get('senses', []):
            # Usage examples written by Wiktionary contributors. Quotations from
            # external books/news retain separate copyright and are not imported.
            for example in sense.get('examples', []):
                text = example.get('text') or ''
                if example.get('type') != 'example' or not 12 <= len(text) <= 180:
                    continue
                if any(c in text for c in ['[', ']', '{', '}', '#', '\n', '\u2003', '/', '^', '…', 'ſ']):
                    continue
                if len(text.split()) < 3:
                    continue
                score = sentence_score(text, ranks) + (300 if entry.get('pos') == parts[word] else 900)
                if text[-1:] not in '.?!':
                    score += 2000
                add_candidate(candidates, word, text, score, source='Wiktionary',
                              source_url=f'https://en.wiktionary.org/wiki/{quote(entry["word"])}#English',
                              author='Wiktionary contributors', license='CC-BY-SA-4.0')


def pick_examples(pool: list) -> list[dict]:
    selected = []
    for _, item in pool:
        tokens = set(TOKEN.findall(item['example'].lower()))
        if any(len(tokens & prev) / max(1, len(tokens | prev)) > 0.65 for prev in
               [set(TOKEN.findall(x['example'].lower())) for x in selected]):
            continue
        selected.append(item)
        if len(selected) == 2:
            break
    return selected


def write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open('w', encoding='utf-8', newline='') as target:
        writer = csv.DictWriter(target, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def build(dictionary: Path, authored: Path, sources: Path, *, kaikki: Path | None = None,
          tatoeba: Path | None = None, cc0: Path | None = None) -> None:
    words = read_csv(dictionary)
    ranks = {w['english']: int(w['frequency_rank']) for w in words}
    overrides = defaultdict(list)
    for row in read_csv(authored):
        word, text = row['english'], row['example']
        if word not in ranks or not contains_word(text, word):
            raise ValueError(f'Invalid authored example for {word}: {text}')
        overrides[word].append(dict(english=word, example=text, source='Recall',
                                    source_url='', author='Recall contributors', license='CC0-1.0'))
    candidates = defaultdict(list)
    if cc0:
        collect_tatoeba(cc0, candidates, ranks, cc0=True)
    if tatoeba:
        collect_tatoeba(tatoeba, candidates, ranks, cc0=False)
    if kaikki:
        collect_kaikki(kaikki, candidates, ranks, {w['english']: w['pos'] for w in words})
    provenance = []
    missing = []
    for word in words:
        examples = overrides[word['english']][:2] or pick_examples(candidates[word['english']])
        if not examples:
            missing.append(word['english'])
        word['example'] = '\n'.join(item['example'] for item in examples)
        provenance.extend(examples)
    if missing:
        raise ValueError(f'{len(missing)} words without usage examples: {missing}')
    write_csv(dictionary, list(words[0]), words)
    write_csv(sources, SOURCE_FIELDS, provenance)
    print(f'Wrote {len(provenance)} examples for {len(words)} words')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dictionary', type=Path, default=Path('data/dictionary.csv'))
    parser.add_argument('--authored', type=Path, default=Path('data/authored_examples.csv'))
    parser.add_argument('--sources', type=Path, default=Path('data/example_sources.csv'))
    parser.add_argument('--kaikki', type=Path)
    parser.add_argument('--tatoeba', type=Path)
    parser.add_argument('--cc0', type=Path)
    args = parser.parse_args()
    build(args.dictionary, args.authored, args.sources, kaikki=args.kaikki, tatoeba=args.tatoeba, cc0=args.cc0)
