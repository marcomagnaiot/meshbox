"""Arma docs/manual.pdf a partir de docs/manual.md.

    uv run --no-project --with markdown python scripts/manual_pdf.py

Convierte el Markdown a HTML con un diseño de impresión (portada, índice, un capítulo por página,
capturas con epígrafe) y lo imprime con el Chromium de Playwright del frontend
(frontend/scripts/html-a-pdf.mjs).
"""

from __future__ import annotations

import html
import re
import subprocess
import sys
import tempfile
import tomllib
from datetime import date
from pathlib import Path

import markdown
from markdown.extensions.toc import slugify_unicode

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
REPO = "https://github.com/marcomagnaiot/meshbox/blob/main/docs/"
MESES = "enero febrero marzo abril mayo junio julio agosto septiembre octubre noviembre diciembre"

CSS = """
@page { size: A4; margin: 16mm 16mm 18mm; }
:root { --ink: #12232a; --ink-2: #4a5d65; --line: #d5e0e4; --accent: #0b7f93; --soft: #eef6f8; }
* { box-sizing: border-box; }
html { font: 10.5pt/1.55 "Source Sans 3", "Segoe UI", system-ui, sans-serif; color: var(--ink); }
body { margin: 0; }
h1, h2, h3 { font-family: "Archivo Narrow", "Arial Narrow", "Segoe UI", sans-serif; line-height: 1.2; }
h2 { break-before: page; font-size: 22pt; margin: 0 0 4mm; padding-bottom: 2mm;
     border-bottom: 2px solid var(--accent); }
h3 { font-size: 13.5pt; margin: 6mm 0 2mm; color: var(--accent); break-after: avoid; }
p, li { orphans: 3; widows: 3; }
p { margin: 0 0 3mm; }
ul, ol { margin: 0 0 3mm; padding-left: 6mm; }
li { margin-bottom: 1mm; }
a { color: var(--accent); text-decoration: none; }
code { font-family: "JetBrains Mono", Consolas, monospace; font-size: 0.86em;
       background: var(--soft); padding: 0.1em 0.35em; border-radius: 3px; }
pre { background: #10232a; color: #d7f0f4; padding: 3.5mm 4mm; border-radius: 4px;
      white-space: pre-wrap; overflow-wrap: anywhere; break-inside: avoid; margin: 0 0 4mm; }
pre code { background: none; padding: 0; color: inherit; font-size: 8.6pt; line-height: 1.5; }
table { width: 100%; border-collapse: collapse; margin: 0 0 4mm; font-size: 9.4pt; break-inside: avoid; }
th { text-align: left; background: var(--soft); color: var(--ink); font-weight: 600; }
th, td { border: 1px solid var(--line); padding: 1.6mm 2.4mm; vertical-align: top; }
figure { margin: 2mm 0 5mm; break-inside: avoid; text-align: center; }
figure img { max-width: 100%; max-height: 190mm; border: 1px solid var(--line); border-radius: 3px; }
figcaption { font-size: 8.8pt; color: var(--ink-2); margin-top: 1.5mm; }
.pair { display: flex; gap: 6mm; justify-content: center; break-inside: avoid; margin: 2mm 0 5mm; }
.pair figure { margin: 0; flex: 0 1 62mm; }
.pair img { max-height: 125mm; }
.cover { height: 260mm; display: flex; flex-direction: column; justify-content: space-between; }
.cover .brand { display: flex; align-items: center; gap: 4mm; font: 600 14pt "Archivo Narrow", sans-serif;
                color: var(--accent); letter-spacing: 0.02em; }
.cover .brand img { width: 13mm; height: 13mm; }
.cover h1 { font-size: 40pt; margin: 14mm 0 3mm; }
.cover .lead { font-size: 13pt; color: var(--ink-2); max-width: 150mm; margin: 0; }
.cover .hero { width: 100%; border-radius: 4px; border: 1px solid var(--line); margin-top: 10mm; }
.cover .meta { display: flex; justify-content: space-between; font-size: 9.5pt; color: var(--ink-2);
               border-top: 1px solid var(--line); padding-top: 3mm; }
.intro { break-before: page; }
.intro h2 { break-before: auto; }
.toc ol { list-style: none; padding: 0; columns: 1; }
.toc li { display: flex; gap: 3mm; padding: 1.6mm 0; border-bottom: 1px dotted var(--line); font-size: 11pt; }
.toc li span { color: var(--accent); font-weight: 600; min-width: 8mm; }
"""


def version() -> str:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def to_html(md_text: str) -> tuple[str, list[tuple[str, str]]]:
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "toc", "attr_list", "md_in_html"],
        extension_configs={"toc": {"slugify": slugify_unicode}},
    )
    body = md.convert(md_text)
    chapters = [(t["id"], t["name"]) for t in md.toc_tokens[0]["children"]] if md.toc_tokens else []
    return body, chapters


def polish(body: str, img_dir: Path) -> str:
    # Primer título, versión y el índice de Markdown: los reemplazan la portada y el índice propio.
    body = re.sub(r"<h1[^>]*>.*?</h1>", "", body, count=1, flags=re.S)
    body = re.sub(r'<h2 id="índice">.*?</ol>', "", body, count=1, flags=re.S)
    body = re.sub(r"<p>Versión del manual:.*?</p>", "", body, count=1, flags=re.S)

    def attr(tag: str, name: str) -> str:
        found = re.search(rf'{name}="([^"]*)"', tag)
        return found.group(1) if found else ""

    def fig(tag: str) -> str:
        alt = attr(tag, "alt")
        return f'<figure><img src="{attr(tag, "src")}" alt="{alt}"><figcaption>{alt}</figcaption></figure>'

    # Dos capturas del celular lado a lado, después las sueltas.
    body = re.sub(
        r"<p>\s*(<img [^>]+>)\s*(<img [^>]+>)\s*</p>",
        lambda m: f'<div class="pair">{fig(m.group(1))}{fig(m.group(2))}</div>',
        body,
    )
    body = re.sub(r"<p>\s*(<img [^>]+>)\s*</p>", lambda m: fig(m.group(1)), body)
    body = body.replace('src="manual/img/', f'src="{img_dir.as_uri()}/')
    body = re.sub(
        r'href="(?!https?:|#)([^"#]+\.(?:md|pdf))(#[^"]*)?"',
        lambda m: f'href="{REPO}{m.group(1)}{m.group(2) or ""}"',
        body,
    )
    return body


def build() -> Path:
    v = version()
    today = date.today()
    fecha = f"{MESES.split()[today.month - 1]} de {today.year}"
    body, chapters = to_html((DOCS / "manual.md").read_text(encoding="utf-8"))
    body = polish(body, DOCS / "manual" / "img")
    first_p = re.search(r"<p>(.*?)</p>", body, flags=re.S)
    lead = first_p.group(1) if first_p else ""
    body = body.replace(first_p.group(0), "", 1) if first_p else body
    logo = (ROOT / "frontend" / "static" / "favicon.svg").as_uri()
    hero = (DOCS / "manual" / "img" / "sitio-mapa.jpg").as_uri()
    toc = "".join(
        f'<li><span>{html.escape(n.split(".", 1)[0])}</span><a href="#{i}">'
        f"{html.escape(n.split('.', 1)[1].strip() if '.' in n else n)}</a></li>"
        for i, n in chapters
        if n[0].isdigit()
    )
    page = f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>Manual de meshbox {v}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo+Narrow:wght@600;700&family=JetBrains+Mono:wght@400&family=Source+Sans+3:wght@400;600&display=swap">
<style>{CSS}</style></head><body>
<section class="cover">
  <div>
    <div class="brand"><img src="{logo}" alt="">meshbox</div>
    <h1>Manual de meshbox</h1>
    <p class="lead">{lead}</p>
    <img class="hero" src="{hero}" alt="">
  </div>
  <div class="meta"><span>Versión {v} · {fecha}</span><span>github.com/marcomagnaiot/meshbox</span></div>
</section>
<section class="intro toc"><h2>Índice</h2><ol>{toc}</ol></section>
{body}
</body></html>"""
    out = Path(tempfile.mkdtemp(prefix="meshbox-manual-")) / "manual.html"
    out.write_text(page, encoding="utf-8")
    return out


def main() -> int:
    page = build()
    pdf = DOCS / "manual.pdf"
    footer = f"Manual de meshbox {version()}"
    subprocess.run(
        ["node", "scripts/html-a-pdf.mjs", str(page), str(pdf), footer],
        cwd=ROOT / "frontend",
        check=True,
    )
    print(f"{pdf} ({pdf.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
