# Copyright (c) 2026 Marco Armijo (R-Mijo). All rights reserved.
# SPDX-License-Identifier: LicenseRef-Proprietary
"""Optional local English PERSON recognition. No content is sent to a service."""
from functools import lru_cache
from importlib.util import find_spec
from threading import RLock

_lock = RLock()


def available():
    return find_spec('spacy') is not None and find_spec('en_core_web_sm') is not None


@lru_cache(maxsize=1)
def _model():
    if not available():
        raise ValueError('Automatic names need local setup: install Scrubbee[names] and run python -m spacy download en_core_web_sm. No name scan was completed.')
    import spacy
    try:
        return spacy.load('en_core_web_sm', exclude=['parser','tagger','attribute_ruler','lemmatizer'])
    except (OSError, ValueError) as error:
        raise ValueError('The local English name model could not load. Reinstall the model before using automatic names.') from error


def person_spans(text):
    if len(text) > 1000000:
        raise ValueError('Automatic name detection supports at most 1,000,000 characters per text block. Split this content before processing.')
    spans = set()
    with _lock:
        model = _model()
        # Overlap avoids dropping names cut by a processing boundary.
        for start in range(0, len(text), 49000):
            doc = model(text[start:start+50000])
            for ent in doc.ents:
                if ent.label_ != 'PERSON':
                    continue
                # Small NER models sometimes call form labels people. Preserve
                # these labels only when immediately followed by a colon.
                if ent.text.strip().casefold() in {'email','phone','address','patient','member','name','date','dob','ssn'} and text[start+ent.end_char:].lstrip().startswith(':'):
                    continue
                spans.add((start+ent.start_char,start+ent.end_char))
    return sorted(spans)
