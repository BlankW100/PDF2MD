"""Markdown rendering — assembles extracted Items into a document."""
from __future__ import annotations
import re

from core.compressor import compress_text, count_tokens

_MULTINL = re.compile(r"\n{3,}")


def md_escape_cell(s: str) -> str:
    return s.replace("\\", "\\\\").replace("|", "\\|").replace("\n", " ").strip()


def table_to_md(rows: list[list[str | None]]) -> str:
    rows = [[md_escape_cell(c or "") for c in r] for r in rows if r is not None]
    rows = [r for r in rows if any(c for c in r)]
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    header, body = rows[0], rows[1:]
    out = ["| " + " | ".join(header) + " |",
           "| " + " | ".join("---" for _ in header) + " |"]
    for r in body:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)


def render_markdown(items_by_page, title: str, opts, out_fh=None) -> tuple[str, dict]:
    """Render Items into Markdown.
    If out_fh is given, stream directly to file (lazy-load, low memory).
    Returns (md_text_or_empty, stats).
    """
    stats = {"chars": 0, "lines": 0, "tokens": 0}

    if not out_fh:
        parts: list[str] = []

    def emit(text: str):
        if out_fh:
            out_fh.write(text)
        else:
            parts.append(text)
        stats["chars"] += len(text)
        stats["lines"] += text.count("\n")

    if title:
        emit(f"# {title}\n")

    last_kind = None
    for pnum, items in enumerate(items_by_page, start=1):
        items.sort(key=lambda it: (round(it.y / 3), it.x))
        if opts.page_marks and items:
            emit(f"\n<!-- page {pnum} -->\n")
        for it in items:
            if it.kind == "heading":
                part = f"\n{'#' * (it.level + 1)} {it.text}\n"
            elif it.kind == "table":
                part = "\n" + it.text + "\n"
            elif it.kind == "image":
                if opts.compress == "aggressive":
                    continue
                part = "\n" + it.text + "\n"
            else:
                txt = compress_text(it.text, opts.compress)
                if not txt:
                    continue
                if it.meta.get("bold") and len(txt) <= 120 and last_kind != "text":
                    txt = f"**{txt}**"
                part = txt + "\n"
            emit(part)
            last_kind = it.kind

    if out_fh:
        return "", stats

    md = _MULTINL.sub("\n\n", "\n".join(parts))
    final = md.strip() + "\n"
    stats["tokens"] = count_tokens(final)
    return final, stats
