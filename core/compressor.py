"""Algorithmic token counting and compression — no AI required."""
from __future__ import annotations
import os
import re
import sys

try:
    import fitz
except ImportError:
    sys.exit("PyMuPDF is required: pip install PyMuPDF")

try:
    import tiktoken
    # encoding_for_model downloads a cache file at first use;
    # in a PyInstaller EXE that cache isn't bundled, so catch any failure.
    _TOKENIZER = tiktoken.encoding_for_model("gpt-4")
except Exception:
    _TOKENIZER = None

_WS = re.compile(r"[ \t ]+")
_MULTINL = re.compile(r"\n{3,}")

_FILLER = {
    "the", "a", "an", "and", "or", "but", "is", "are", "was", "were",
    "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "will", "would", "could", "should", "may", "might", "can", "must",
    "also", "just", "only", "very", "quite", "rather", "somewhat",
    "however", "therefore", "moreover", "furthermore", "thus",
}


def count_tokens(text: str) -> int:
    """Count tokens using tiktoken; falls back to char/4 estimate if not installed."""
    if _TOKENIZER is None:
        return max(1, len(text) // 4)
    try:
        return len(_TOKENIZER.encode(text))
    except Exception:
        return max(1, len(text) // 4)


def compress_text(text: str, mode: str) -> str:
    """In-line text compression. Modes: off | balanced | aggressive."""
    if mode == "off":
        return text
    if mode == "balanced":
        return _WS.sub(" ", text).strip()
    if mode == "aggressive":
        words = text.split()
        return " ".join(
            w for w in words
            if w.lower().strip(".,;:!?\"'()") not in _FILLER
        ).strip()
    return text


def estimate_pdf_tokens(path: str) -> int:
    """Fast raw-text token estimate from a PDF (no layout processing)."""
    doc = fitz.open(path)
    raw = "".join(page.get_text() for page in doc)
    doc.close()
    return count_tokens(raw)


def compress_md_file(path: str, mode: str) -> tuple[str, dict, dict]:
    """Algorithmically compress an existing Markdown file.
    Returns (out_path, before_stats, after_stats).
    """
    with open(path, "r", encoding="utf-8") as fh:
        original = fh.read()

    before = {"tokens": count_tokens(original), "chars": len(original)}

    text = original
    # Always: strip trailing spaces, collapse excess blank lines
    text = "\n".join(line.rstrip() for line in text.splitlines())
    text = _MULTINL.sub("\n\n", text)

    if mode in ("balanced", "aggressive"):
        # Remove <!-- page N --> comments (pure overhead for LLMs)
        text = re.sub(r"\n?<!-- page \d+ -->\n?", "\n", text)
        # Collapse inline whitespace in text lines (skip code blocks and tables)
        lines, in_code = [], False
        for line in text.splitlines():
            if line.startswith("```"):
                in_code = not in_code
            if not in_code and not line.startswith("|"):
                line = _WS.sub(" ", line).rstrip()
            lines.append(line)
        text = "\n".join(lines)

    if mode == "aggressive":
        # Remove filler words from body text (headings, tables, code untouched)
        lines, in_code = [], False
        for line in text.splitlines():
            if line.startswith("```"):
                in_code = not in_code
            if not in_code and not line.startswith("#") and not line.startswith("|"):
                words = line.split()
                line = " ".join(
                    w for w in words
                    if w.lower().strip(".,;:!?\"'()") not in _FILLER
                )
            lines.append(line)
        text = "\n".join(lines)

    text = _MULTINL.sub("\n\n", text).strip() + "\n"

    stem = os.path.splitext(path)[0]
    out_path = f"{stem}_compressed.md"
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(text)

    after = {"tokens": count_tokens(text), "chars": len(text)}
    return out_path, before, after
