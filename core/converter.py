"""High-level PDF conversion driver."""
from __future__ import annotations
import os
import sys
import time

try:
    import fitz
except ImportError:
    sys.exit("PyMuPDF is required: pip install PyMuPDF")

from core.extractor import collect_running_lines, dominant_body_size, parse_page
from core.renderer import render_markdown
from core.compressor import estimate_pdf_tokens, count_tokens
from core.vision import ImageBrain


def convert(path: str, opts) -> tuple[str, list[str], dict]:
    """Convert a PDF to Markdown. Returns (out_path, warnings, stats)."""
    start_time = time.time()
    pdf_tokens = estimate_pdf_tokens(path)
    doc = fitz.open(path)
    opts._warnings = []

    stem = os.path.splitext(os.path.basename(path))[0]
    out_path = opts.output or os.path.join(os.path.dirname(path) or ".", stem + ".md")

    assets_dir = None
    if opts.images == "extract":
        assets_dir = os.path.join(os.path.dirname(out_path) or ".", stem + "_assets")

    brain = ImageBrain(
        mode=opts.images if opts.images in ("ocr", "describe") else "off",
        model=opts.model,
        ocr_engine=opts.ocr_engine,
    )
    body_size = dominant_body_size(doc)
    running = collect_running_lines(doc)

    pages: list = []
    for page_num, page in enumerate(doc, start=1):
        try:
            pages.append(parse_page(page, body_size, running, brain,
                                    assets_dir, stem, opts))
        except Exception as e:
            from core.extractor import Item
            pages.append([Item(y=0, x=0, kind="text",
                               text=f"<!-- page {page_num} failed: {e} -->")])
        if opts.verbose:
            elapsed = time.time() - start_time
            est_remain = (elapsed / page_num) * (doc.page_count - page_num)
            print(f"  page {page_num}/{doc.page_count}  "
                  f"({elapsed:.1f}s elapsed, ~{est_remain:.0f}s remaining)",
                  file=sys.stderr)

    title = (doc.metadata or {}).get("title") or stem

    # Stream pages to disk — avoids holding the full document in memory
    with open(out_path, "w", encoding="utf-8") as fh:
        _, stats = render_markdown(pages, title if opts.title else "", opts, out_fh=fh)

    # Read back once to count tokens (streaming left md="" in memory)
    with open(out_path, "r", encoding="utf-8") as fh:
        content = fh.read()
    stats["tokens"] = count_tokens(content)
    stats["chars"] = len(content)
    stats["lines"] = content.count("\n")
    stats["pdf_tokens"] = pdf_tokens
    # A scanned/image PDF has almost no text layer; raw token count will be tiny.
    # Threshold: fewer than 80 tokens for the whole document = effectively image-only.
    stats["is_scanned"] = pdf_tokens < 80
    stats["elapsed"] = time.time() - start_time

    doc.close()
    return out_path, list(opts._warnings), stats
