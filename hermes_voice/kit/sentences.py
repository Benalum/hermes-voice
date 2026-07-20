"""Sentence chunking for streaming TTS: speak sentence n while synthesizing n+1."""

from __future__ import annotations

import re

_SENTENCE_END = re.compile(r"[.!?…]+(?=\s|$)")

_ABBREVIATIONS = frozenset(
    {
        "dr",
        "mr",
        "mrs",
        "ms",
        "prof",
        "sr",
        "jr",
        "st",
        "vs",
        "etc",
        "e.g",
        "i.e",
        "eg",
        "ie",
        "no",
        "inc",
        "ltd",
        "dept",
        "approx",
    }
)


def _last_word(text: str) -> str:
    parts = text.split()
    return parts[-1] if parts else ""


def _split_line(line: str) -> list[str]:
    sentences: list[str] = []
    start = 0
    for match in _SENTENCE_END.finditer(line):
        preceding = _last_word(line[start : match.start()])
        if preceding.lower() in _ABBREVIATIONS:
            continue
        sentence = " ".join(line[start : match.end()].split())
        if sentence:
            sentences.append(sentence)
        start = match.end()
    tail = " ".join(line[start:].split())
    if tail:
        sentences.append(tail)
    return sentences


def split_sentences(text: str) -> tuple[str, ...]:
    return tuple(sentence for line in text.splitlines() for sentence in _split_line(line))
