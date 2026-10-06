"""Split spoken text into TTS-sized requests without losing any words."""
from __future__ import annotations

from ..text_utils import split_sentences


def chunk_for_tts(text: str, max_chars: int = 4000) -> list[str]:
    """Pack whole sentences into chunks of at most ``max_chars`` characters.

    A sentence longer than the limit is split at word boundaries. Joining the chunks with
    spaces reproduces the original text (modulo whitespace).
    """
    if max_chars < 20:
        raise ValueError("max_chars is unrealistically small")
    text = " ".join((text or "").split())
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]
    pieces: list[str] = []
    for sentence in split_sentences(text):
        if len(sentence) <= max_chars:
            pieces.append(sentence)
            continue
        line = ""
        for word in sentence.split(" "):
            while len(word) > max_chars:  # a single absurdly long token
                if line:
                    pieces.append(line)
                    line = ""
                pieces.append(word[:max_chars])
                word = word[max_chars:]
            if line and len(line) + 1 + len(word) > max_chars:
                pieces.append(line)
                line = word
            else:
                line = f"{line} {word}".strip()
        if line:
            pieces.append(line)
    chunks: list[str] = []
    for piece in pieces:
        if chunks and len(chunks[-1]) + 1 + len(piece) <= max_chars:
            chunks[-1] = f"{chunks[-1]} {piece}"
        else:
            chunks.append(piece)
    return chunks
