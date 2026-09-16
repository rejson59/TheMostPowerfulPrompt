#!/usr/bin/env python3
"""
build.py — renders prompt/*.md into index.html (single, dependency-free page).

Usage:  python3 build.py
Output: index.html
"""

from __future__ import annotations

import html
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "index.html"

SOURCES = [
    {"lang": "en", "label": "English", "file": ROOT / "prompt" / "EN.md"},
    {"lang": "pl", "label": "Polski", "file": ROOT / "prompt" / "PL.md"},
]


# --------------------------------------------------------------------------
# inline rendering
# --------------------------------------------------------------------------

def render_inline(text: str) -> str:
    """Escape HTML, then apply inline markdown: `code`, **bold**, *italic*."""
    # protect inline code spans first so their contents are never styled
    placeholders: list[str] = []

    def stash(match: re.Match[str]) -> str:
        placeholders.append(match.group(1))
        return f"\x00{len(placeholders) - 1}\x00"

    text = re.sub(r"`([^`]+)`", stash, text)
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<em>\1</em>", text)

    def restore(match: re.Match[str]) -> str:
        return f"<code>{html.escape(placeholders[int(match.group(1))], quote=False)}</code>"

    return re.sub(r"\x00(\d+)\x00", restore, text)


def slugify(text: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[\s_-]+", "-", slug).strip("-")
    return slug or "section"


# --------------------------------------------------------------------------
# block rendering
# --------------------------------------------------------------------------

def render_blocks(lines: list[str]) -> tuple[str, list[dict]]:
    """Render a list of markdown lines to HTML. Returns (html, toc_entries)."""
    out: list[str] = []
    toc: list[dict] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]

        # fenced code block
        if line.lstrip().startswith("```"):
            lang = line.strip()[3:].strip()
            i += 1
            buf: list[str] = []
            while i < n and not lines[i].lstrip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1  # closing fence
            cls = f' class="lang-{lang}"' if lang else ""
            code = html.escape("\n".join(buf), quote=False)
            out.append(
                '<div class="codeblock"><div class="codebar">'
                f"<span>{html.escape(lang or 'text')}</span>"
                '<button class="copy-mini" data-copy-code>Kopiuj</button></div>'
                f"<pre><code{cls}>{code}</code></pre></div>"
            )
            continue

        # horizontal rule / separator banners
        if re.match(r"^===\s.*\s===$", line.strip()):
            out.append(f'<div class="banner">{render_inline(line.strip())}</div>')
            i += 1
            continue

        if re.match(r"^-{3,}$", line.strip()):
            out.append("<hr>")
            i += 1
            continue

        # heading
        m = re.match(r"^(#{1,4})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            text = m.group(2).strip()
            anchor = slugify(text)
            out.append(f'<h{level} id="{anchor}">{render_inline(text)}</h{level}>')
            if level in (2, 3):
                toc.append({"level": level, "text": text, "id": anchor})
            i += 1
            continue

        # blockquote
        if line.lstrip().startswith(">"):
            buf = []
            while i < n and lines[i].lstrip().startswith(">"):
                buf.append(re.sub(r"^\s*>\s?", "", lines[i]))
                i += 1
            inner, _ = render_blocks(buf)
            out.append(f"<blockquote>{inner}</blockquote>")
            continue

        # table
        if "|" in line and i + 1 < n and re.match(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", lines[i + 1]):
            def cells(row: str) -> list[str]:
                row = row.strip()
                if row.startswith("|"):
                    row = row[1:]
                if row.endswith("|"):
                    row = row[:-1]
                return [c.strip() for c in row.split("|")]

            head = cells(line)
            i += 2
            body: list[list[str]] = []
            while i < n and "|" in lines[i] and lines[i].strip():
                body.append(cells(lines[i]))
                i += 1
            thead = "".join(f"<th>{render_inline(c)}</th>" for c in head)
            rows = "".join(
                "<tr>" + "".join(f"<td>{render_inline(c)}</td>" for c in row) + "</tr>"
                for row in body
            )
            out.append(
                f'<div class="tablewrap"><table><thead><tr>{thead}</tr></thead>'
                f"<tbody>{rows}</tbody></table></div>"
            )
            continue

        # list (unordered or ordered)
        if re.match(r"^\s*([-*]|\d+\.)\s+", line):
            ordered = bool(re.match(r"^\s*\d+\.\s+", line))
            tag = "ol" if ordered else "ul"
            items: list[str] = []
            while i < n and re.match(r"^\s*([-*]|\d+\.)\s+", lines[i]):
                item = re.sub(r"^\s*([-*]|\d+\.)\s+", "", lines[i])
                i += 1
                # absorb continuation lines
                while (
                    i < n
                    and lines[i].strip()
                    and not re.match(r"^\s*([-*]|\d+\.)\s+", lines[i])
                    and not re.match(r"^(#{1,4})\s", lines[i])
                    and not lines[i].lstrip().startswith(">")
                    and not lines[i].lstrip().startswith("```")
                    and re.match(r"^\s{2,}\S", lines[i])
                ):
                    item += " " + lines[i].strip()
                    i += 1
                items.append(f"<li>{render_inline(item)}</li>")
            out.append(f"<{tag}>" + "".join(items) + f"</{tag}>")
            continue

        # blank
        if not line.strip():
            i += 1
            continue

        # paragraph
        buf = []
        while (
            i < n
            and lines[i].strip()
            and not re.match(r"^(#{1,4})\s", lines[i])
            and not re.match(r"^\s*([-*]|\d+\.)\s+", lines[i])
            and not lines[i].lstrip().startswith(">")
            and not lines[i].lstrip().startswith("```")
            and not re.match(r"^-{3,}$", lines[i].strip())
            and not re.match(r"^===\s.*\s===$", lines[i].strip())
        ):
            buf.append(lines[i].strip())
            i += 1
        out.append(f"<p>{render_inline(' '.join(buf))}</p>")

    return "\n".join(out), toc


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def extract_sections(raw: str) -> dict[str, str]:
    """Map each `## ` heading slug to its raw markdown, up to the next `## `.

    Computed here (in Python) rather than in the page's JS so that the slugs are
    guaranteed to match the ones the renderer emitted — JS `\\w` is ASCII-only
    and would silently mis-slug non-English headings.
    """
    lines = raw.splitlines()
    marks: list[tuple[str, int]] = []
    in_fence = False
    for idx, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = re.match(r"^##\s+(.*)$", line)
        if m:
            marks.append((slugify(m.group(1).strip()), idx))

    sections: dict[str, str] = {}
    for i, (slug, start) in enumerate(marks):
        end = marks[i + 1][1] if i + 1 < len(marks) else len(lines)
        sections[slug] = "\n".join(lines[start:end]).strip()
    return sections


def extract_variants(raw: str) -> dict[str, str]:
    """Pull the ready-to-paste variants out of the appendix code blocks.

    Keyed by a stable name derived from the heading the block sits under, so the
    page and the standalone .txt files stay in sync with one source of truth.
    """
    variants: dict[str, str] = {}
    lines = raw.splitlines()
    heading = ""
    i = 0
    while i < len(lines):
        m = re.match(r"^#{2,3}\s+(.*)$", lines[i])
        if m:
            heading = m.group(1).strip()
        if lines[i].lstrip().startswith("```"):
            i += 1
            buf: list[str] = []
            while i < len(lines) and not lines[i].lstrip().startswith("```"):
                buf.append(lines[i])
                i += 1
            name = "LITE" if "LITE" in heading.upper() or "SKRÓCON" in heading.upper() \
                else "ONELINE" if "ONE-LINE" in heading.upper() or "JEDNOZDANIOW" in heading.upper() \
                else slugify(heading)
            variants[name] = "\n".join(buf).strip() + "\n"
        i += 1
    return variants


def word_count(text: str) -> int:
    """Count words outside of code fences (a fairer measure of prose size)."""
    stripped = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    return len(re.findall(r"\S+", stripped))


def token_estimate(text: str) -> int:
    # rough heuristic: ~4 chars/token for English prose, ~5.5 for Polish
    return int(len(text) / 4.0)


def build_doc(entry: dict) -> dict:
    raw = entry["file"].read_text(encoding="utf-8")
    # keep the size claim in the header honest and self-updating
    raw = raw.replace("{{TOKENS}}", f"{token_estimate(raw):,}")
    body, toc = render_blocks(raw.splitlines())
    return {
        "lang": entry["lang"],
        "label": entry["label"],
        "raw": raw,
        "body": body,
        "toc": toc,
        "words": word_count(raw),
        "chars": len(raw),
        "tokens": token_estimate(raw),
        "sectionText": extract_sections(raw),
        "variants": extract_variants(raw),
        "sections": len([t for t in toc if t["level"] == 2]),
    }


def main() -> None:
    docs = [build_doc(e) for e in SOURCES]
    template = (ROOT / "template.html").read_text(encoding="utf-8")

    # `<` -> \u003c keeps a literal "</script>" inside the prompt from
    # terminating the <script type="application/json"> block early.
    docs_json = json.dumps(docs, ensure_ascii=False).replace("<", "\\u003c")

    replacements = {
        "@@DOCS@@": docs_json,
        "@@TOTAL_WORDS@@": f"{sum(d['words'] for d in docs):,}",
        "@@TOTAL_CHARS@@": f"{sum(d['chars'] for d in docs):,}",
        "@@TOTAL_TOKENS@@": f"{sum(d['tokens'] for d in docs):,}",
        "@@TOTAL_SECTIONS@@": str(sum(d["sections"] for d in docs)),
        "@@EN_WORDS@@": f"{docs[0]['words']:,}",
        "@@EN_TOKENS@@": f"{docs[0]['tokens']:,}",
        "@@PL_WORDS@@": f"{docs[1]['words']:,}",
    }
    page = template
    for key, value in replacements.items():
        page = page.replace(key, value)

    # standalone ready-to-paste variants, one file per variant
    vdir = ROOT / "prompt" / "variants"
    vdir.mkdir(parents=True, exist_ok=True)
    for d in docs:
        for name, text in d["variants"].items():
            (vdir / f"{d['lang'].upper()}-{name}.txt").write_text(text, encoding="utf-8")

    OUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes / {len(page):,} chars)")
    for d in docs:
        print(
            f"  {d['lang']}: {d['words']:,} words | {d['chars']:,} chars | "
            f"~{d['tokens']:,} tokens | {d['sections']} top-level sections | "
            f"{len(d['toc'])} TOC entries | "
            f"variants: {', '.join(sorted(d['variants'])) or 'none'}"
        )


if __name__ == "__main__":
    main()
