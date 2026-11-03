"""Dictionary-backed English tokenization; no message text leaves the bot."""
from __future__ import annotations

import csv
import re
from collections import defaultdict
from pathlib import Path

CONTENT_POS = {'noun', 'verb', 'adj', 'adv', 'phrasal'}
STOP_WORDS = frozenset('''a an the and or but if then than that this these those
    i me my mine myself we us our ours ourselves you your yours yourself yourselves
    he him his himself she her hers herself it its itself they them their theirs themselves
    who whom whose what which where when why how here there yes no not nor
    in on at to of for from by with without about as into onto over under through
    before after during between among against around until since per via
    be am is are was were been being have has had having do does did doing done
    can could may might must shall should will would ought need dare
    very too so just also even ever never always already still yet only much many
    more most less least some any all both each every either neither other another
    up down out off away again well good better best worse worst
    im ive ill id youre youve youll youd hes shes its thats dont doesnt didnt
    cant couldnt wont wouldnt shouldnt isnt arent wasnt werent havent hasnt hadnt
'''.split())
DETERMINERS = frozenset('a an the this that these those my your his her its our their'.split())
BASE_VERBS = frozenset('to can could may might must shall should will would'.split())
VERB_CONTEXT = BASE_VERBS | frozenset('i you he she we they am is are was were be been have has had'.split())
TOKEN = re.compile(r"(?<![\w'’-])[A-Za-z]+(?:['’-][A-Za-z]+)*(?![\w'’-])")
LINK = re.compile(r"(?:https?://|www\.)\S+|\b\S+@\S+\.\S+|(?<!\w)[@#/]\w+", re.I)
CODE = re.compile(r'```[\s\S]*?```|`[^`\n]*`')
EXCLUDED_ENTITIES = {'url', 'text_link', 'email', 'mention', 'hashtag', 'cashtag',
                     'bot_command', 'code', 'pre', 'blockquote', 'expandable_blockquote'}


def authored_text(text: str, entities=()) -> str:
    """Telegram offsets are UTF-16, including when emoji precede a link/quote."""
    encoded = bytearray(text.encode('utf-16-le'))
    for entity in entities:
        kind = getattr(entity.type, 'value', entity.type)
        if kind in EXCLUDED_ENTITIES:
            start, end = entity.offset * 2, (entity.offset + entity.length) * 2
            encoded[start:end] = b' \x00' * entity.length
    text = encoded.decode('utf-16-le')
    # Also cover plain-text links/code in synthetic messages or captions.
    text = CODE.sub(' ', text)
    return LINK.sub(' ', text)


class PracticeLexicon:
    def __init__(self, words: list[dict], forms: list[dict]) -> None:
        self.words = {w['english'].lower(): w for w in words}
        self.forms: dict[str, set[tuple[str, str]]] = defaultdict(set)
        for row in forms:
            if row['english'] in self.words:
                self.forms[row['form']].add((row['english'], row['pos']))

    @classmethod
    def from_csv(cls, words: list[dict], path: Path) -> PracticeLexicon:
        with path.open(encoding='utf-8', newline='') as source:
            return cls(words, list(csv.DictReader(source)))

    def lemma(self, surface: str, previous: str = '') -> str | None:
        surface = surface.lower().replace('’', "'")
        if surface.endswith("'s"):
            surface = surface[:-2]
        direct = self.words.get(surface)
        inflected = self.forms.get(surface, set())
        if direct and (previous in BASE_VERBS or previous in DETERMINERS and direct['pos'] == 'noun'):
            return surface
        if len({lemma for lemma, _ in inflected}) > 1:
            wanted_pos = 'noun' if previous in DETERMINERS else 'verb' if previous in VERB_CONTEXT else None
            inflected = {(lemma, pos) for lemma, pos in inflected if pos == wanted_pos}
            if len({lemma for lemma, _ in inflected}) != 1:
                return None  # e.g. axes: axe/axis; no guessed roots.
        if inflected:
            return next(iter(inflected))[0]
        return surface if direct else None

    def extract(self, text: str) -> list[dict]:
        tokens = list(TOKEN.finditer(text))
        found = {}
        i = 0
        while i < len(tokens):
            token = tokens[i]
            previous = (tokens[i - 1].group().lower()
                        if i and text[tokens[i - 1].end():token.start()].isspace() else '')
            lemma = None
            consumed = 1
            # Adjacent phrasal verbs and documented forms such as "gave up".
            for size in (3, 2, 1):
                chunk = tokens[i:i + size]
                if len(chunk) != size:
                    continue
                if any(not text[a.end():b.start()].isspace() for a, b in zip(chunk, chunk[1:])):
                    continue
                surface = ' '.join(t.group().lower() for t in chunk)
                candidate = self.lemma(surface, previous)
                if candidate:
                    lemma, consumed = candidate, size
                    break
            if lemma and lemma not in STOP_WORDS and len(lemma) >= 2:
                word = self.words[lemma]
                if word['pos'] in CONTENT_POS:
                    found[word['id']] = word
            i += consumed
        return list(found.values())
