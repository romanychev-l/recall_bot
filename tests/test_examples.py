from __future__ import annotations

import bz2
import csv
import json
from pathlib import Path

from data.build_examples import build, contains_word, read_csv, write_csv

ROOT = Path(__file__).resolve().parents[1]


def test_every_shipped_word_has_one_or_two_attributed_examples():
    words = read_csv(ROOT / 'data/dictionary.csv')
    sources = read_csv(ROOT / 'data/example_sources.csv')
    provenance = {(r['english'], r['example']): r for r in sources}
    assert len(provenance) == len(sources)
    expected = set()
    for word in words:
        examples = word['example'].splitlines()
        assert 1 <= len(examples) <= 2, word['english']
        assert len(set(examples)) == len(examples)
        for text in examples:
            assert 12 <= len(text) <= 220, (word['english'], text)
            assert contains_word(text, word['english']), (word['english'], text)
            source = provenance[word['english'], text]
            assert source['license'] in {'CC0-1.0', 'CC-BY-2.0-FR', 'CC-BY-SA-4.0'}
            if source['source'] != 'Recall':
                assert source['source_url'].startswith('https://')
            if source['license'] != 'CC0-1.0':
                assert source['author']
            expected.add((word['english'], text))
    assert set(provenance) == expected


def test_builder_selects_whole_words_honors_overrides_and_avoids_book_quotations(tmp_path):
    dictionary = tmp_path / 'words.csv'
    rows = [dict(english=w, translation=t, frequency_rank=i, pos='noun', example='')
            for i, (w, t) in enumerate([('art', 'искусство'), ('cat', 'кот'), ('dog', 'собака')], 1)]
    write_csv(dictionary, list(rows[0]), rows)
    authored = tmp_path / 'authored.csv'
    write_csv(authored, ['english', 'example'], [dict(english='dog', example='The dog waited by the door.')])
    corpus = tmp_path / 'eng.tsv.bz2'
    with bz2.open(corpus, 'wt', encoding='utf-8') as target:
        target.write('1\teng\tThe cart is broken.\tAlice\t0\t0\n')
        target.write('2\teng\tThe cat is sleeping.\tBob\t0\t0\n')
    kaikki = tmp_path / 'kaikki.jsonl'
    kaikki.write_text(json.dumps(dict(word='art', pos='noun', senses=[dict(examples=[
        dict(text='Modern art makes me happy.', type='example'),
        dict(text='This art belongs to a modern novelist.', type='quotation'),
    ])])), encoding='utf-8')
    sources = tmp_path / 'sources.csv'
    build(dictionary, authored, sources, kaikki=kaikki, tatoeba=corpus)
    result = {w['english']: w['example'] for w in read_csv(dictionary)}
    assert result == {'art': 'Modern art makes me happy.', 'cat': 'The cat is sleeping.',
                      'dog': 'The dog waited by the door.'}
    provenance = {r['english']: r for r in read_csv(sources)}
    assert provenance['cat']['author'] == 'Bob'
    assert provenance['art']['license'] == 'CC-BY-SA-4.0'


def test_builder_refuses_partial_coverage_before_writing(tmp_path):
    import pytest
    dictionary = tmp_path / 'words.csv'
    row = dict(english='missing', translation='пропавший', frequency_rank=1, pos='adj', example='')
    write_csv(dictionary, list(row), [row])
    before = dictionary.read_bytes()
    authored = tmp_path / 'authored.csv'
    write_csv(authored, ['english', 'example'], [])
    sources = tmp_path / 'sources.csv'
    with pytest.raises(ValueError, match='1 words without usage examples'):
        build(dictionary, authored, sources)
    assert dictionary.read_bytes() == before
    assert not sources.exists()
