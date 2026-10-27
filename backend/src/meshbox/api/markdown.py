"""Markdown mínimo → bloques JSON (aviso de privacidad, sección 13.5).

El frontend tiene prohibido `{@html}` sobre datos. En vez de HTML saneado, el servidor
devuelve una estructura con una lista blanca: párrafos, títulos (#, ##, ###), listas
(- o *), negrita (**), cursiva (*), código (`) y enlaces http(s) o mailto. El frontend la
dibuja con componentes; nunca interpreta HTML.
"""

from __future__ import annotations

import re
from typing import Any

INLINE_RE = re.compile(
    r"(\*\*(?P<strong>[^*]+)\*\*)|(\*(?P<em>[^*]+)\*)|(`(?P<code>[^`]+)`)|"
    r"(\[(?P<ltext>[^\]]+)\]\((?P<href>[^)\s]+)\))"
)
SAFE_HREF = re.compile(r"^(https?://|mailto:)[^\s<>\"']+$", re.I)
MAX_LEN = 20_000


def inline(text: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    pos = 0
    for m in INLINE_RE.finditer(text):
        if m.start() > pos:
            out.append({"t": "text", "v": text[pos : m.start()]})
        if m.group("strong"):
            out.append({"t": "strong", "v": m.group("strong")})
        elif m.group("em"):
            out.append({"t": "em", "v": m.group("em")})
        elif m.group("code"):
            out.append({"t": "code", "v": m.group("code")})
        else:
            href = m.group("href")
            if SAFE_HREF.match(href):
                out.append({"t": "link", "v": m.group("ltext"), "href": href})
            else:
                out.append({"t": "text", "v": m.group("ltext")})
        pos = m.end()
    if pos < len(text):
        out.append({"t": "text", "v": text[pos:]})
    return out


def to_blocks(md: str | None) -> list[dict[str, Any]]:
    if not md:
        return []
    blocks: list[dict[str, Any]] = []
    para: list[str] = []
    items: list[str] = []

    def flush_para() -> None:
        if para:
            blocks.append({"t": "p", "c": inline(" ".join(para))})
            para.clear()

    def flush_list() -> None:
        if items:
            blocks.append({"t": "ul", "c": [inline(i) for i in items]})
            items.clear()

    for raw in md[:MAX_LEN].splitlines():
        line = raw.strip()
        if not line:
            flush_para()
            flush_list()
            continue
        heading = re.match(r"^(#{1,3})\s+(.*)$", line)
        if heading:
            flush_para()
            flush_list()
            blocks.append({"t": f"h{len(heading.group(1)) + 1}", "c": inline(heading.group(2))})
            continue
        item = re.match(r"^[-*]\s+(.*)$", line)
        if item:
            flush_para()
            items.append(item.group(1))
            continue
        flush_list()
        para.append(line)
    flush_para()
    flush_list()
    return blocks
