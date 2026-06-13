"""PDF page extraction — text, headings, tables, images."""
from __future__ import annotations
import os
import re
import sys
from collections import Counter
from dataclasses import dataclass, field

try:
    import fitz
except ImportError:
    sys.exit("PyMuPDF is required: pip install PyMuPDF")

from core.vision import ImageBrain, squeeze, _to_png

_WS = re.compile(r"[ \t ]+")


@dataclass
class Item:
    """A positioned piece of page content, sorted later into reading order."""
    y: float
    x: float
    kind: str       # 'text' | 'heading' | 'table' | 'image'
    text: str = ""
    level: int = 0
    meta: dict = field(default_factory=dict)


def looks_like_pagenum(s: str) -> bool:
    s = s.strip()
    return bool(re.fullmatch(r"(page\s*)?\d{1,4}(\s*/\s*\d{1,4})?", s, re.I)) or \
        bool(re.fullmatch(r"[-–—]?\s*\d{1,4}\s*[-–—]?", s))


def rects_overlap(a, b, tol: float = 0.0) -> bool:
    return not (a[2] <= b[0] + tol or a[0] >= b[2] - tol or
                a[3] <= b[1] + tol or a[1] >= b[3] - tol)


def _blockquote(s: str) -> str:
    return "\n".join("> " + l for l in s.splitlines())


def _warn(opts, msg: str):
    print(f"  [warn] {msg}", file=sys.stderr)
    bucket = getattr(opts, "_warnings", None)
    if bucket is not None:
        bucket.append(msg)


def collect_running_lines(doc) -> set[str]:
    """Find header/footer lines that repeat across many pages and should be dropped."""
    if doc.page_count < 4:
        return set()
    top, bot = Counter(), Counter()
    for page in doc:
        h = page.rect.height
        d = page.get_text("dict")
        for block in d.get("blocks", []):
            if block.get("type") != 0:
                continue
            y0 = block["bbox"][1]
            txt = squeeze(" ".join(
                s["text"] for line in block["lines"] for s in line["spans"]))
            if not txt or looks_like_pagenum(txt):
                continue
            if y0 < h * 0.10:
                top[txt] += 1
            elif y0 > h * 0.90:
                bot[txt] += 1
    thresh = max(3, int(doc.page_count * 0.5))
    return {t for t, c in (top + bot).items() if c >= thresh}


def dominant_body_size(doc) -> float:
    """Return the most common text font size — used as the heading threshold."""
    sizes = Counter()
    for page in doc:
        for b in page.get_text("dict").get("blocks", []):
            if b.get("type") != 0:
                continue
            for line in b["lines"]:
                for s in line["spans"]:
                    if s["text"].strip():
                        sizes[round(s["size"], 1)] += len(s["text"].strip())
    return sizes.most_common(1)[0][0] if sizes else 11.0


def parse_page(page, body_size: float, running: set[str],
               brain: ImageBrain, assets_dir: str | None,
               img_prefix: str, opts) -> list[Item]:
    """Extract all content from a single PDF page into a list of Items."""
    from core.renderer import table_to_md   # late import avoids circular dep

    items: list[Item] = []

    # Tables first — remember their boxes to mask the text sitting under them
    table_boxes = []
    try:
        tables = page.find_tables()
    except Exception:
        tables = None
    if tables:
        for t in tables:
            try:
                rows = t.extract()
            except Exception:
                continue
            md = table_to_md(rows)
            if md:
                bbox = tuple(t.bbox)
                table_boxes.append(bbox)
                items.append(Item(y=bbox[1], x=bbox[0], kind="table", text=md))

    d = page.get_text("dict")
    blocks = d.get("blocks", [])

    text_chars = sum(len(s["text"].strip())
                     for b in blocks if b.get("type") == 0
                     for ln in b["lines"] for s in ln["spans"])

    for block in blocks:
        if block.get("type") != 0:
            continue
        bbox = block["bbox"]
        if any(rects_overlap(bbox, tb, tol=2) for tb in table_boxes):
            continue
        lines_out, max_size, bold = [], 0.0, False
        for line in block["lines"]:
            spans = line["spans"]
            if not spans:
                continue
            txt = squeeze("".join(s["text"] for s in spans))
            if not txt:
                continue
            for s in spans:
                max_size = max(max_size, s["size"])
                if s["flags"] & 16:
                    bold = True
            lines_out.append(txt)
        if not lines_out:
            continue
        text = squeeze(" ".join(lines_out))
        if not text or text in running or looks_like_pagenum(text):
            continue

        is_heading = (max_size >= body_size * 1.15
                      and len(text) <= 120
                      and len(lines_out) <= 2)
        if is_heading:
            ratio = max_size / body_size
            level = 1 if ratio >= 1.8 else 2 if ratio >= 1.45 else 3 if ratio >= 1.2 else 4
            items.append(Item(y=bbox[1], x=bbox[0], kind="heading", text=text, level=level))
        else:
            items.append(Item(y=bbox[1], x=bbox[0], kind="text", text=text,
                              meta={"bold": bold}))

    pno = page.number + 1
    if opts.images != "off":
        scanned = text_chars < 20
        if scanned and opts.images in ("ocr", "describe"):
            pix = page.get_pixmap(dpi=opts.dpi)
            png = pix.tobytes("png")
            out = brain.process(png, hint="Full scanned page.")
            if out:
                items.append(Item(y=0, x=0, kind="text", text=out))
            else:
                _warn(opts, f"page {pno}: scanned page, no text could be read")
                items.append(Item(y=0, x=0, kind="text",
                    text=f"> ⚠️ Page {pno}: scanned page with no readable text."))
        else:
            for idx, info in enumerate(page.get_images(full=True)):
                xref = info[0]
                try:
                    base = page.parent.extract_image(xref)
                except Exception:
                    continue
                rects = page.get_image_rects(xref)
                y = rects[0].y0 if rects else 1e9
                x = rects[0].x0 if rects else 0
                if base.get("width", 0) * base.get("height", 0) < 64 * 64:
                    continue
                img_bytes = base["image"]
                ext = base.get("ext", "png")
                if opts.images in ("ocr", "describe"):
                    png = img_bytes if ext == "png" else _to_png(img_bytes)
                    out = brain.process(png, hint="Embedded image/figure.")
                    label = "image text" if opts.images == "ocr" else "figure"
                    if out:
                        items.append(Item(y=y, x=x, kind="text",
                                          text=f"> **[{label}]**\n>\n{_blockquote(out)}"))
                    else:
                        _warn(opts, f"page {pno}: image #{idx} has no readable text")
                        items.append(Item(y=y, x=x, kind="text",
                            text=f"> ⚠️ Page {pno}: image with no readable text."))
                    continue
                if assets_dir:
                    os.makedirs(assets_dir, exist_ok=True)
                    name = f"{img_prefix}_p{pno}_{idx}.{ext}"
                    with open(os.path.join(assets_dir, name), "wb") as fh:
                        fh.write(img_bytes)
                    rel = os.path.join(os.path.basename(assets_dir), name).replace("\\", "/")
                    items.append(Item(y=y, x=x, kind="image",
                                      text=f"![figure p{pno}]({rel})"))
    return items
