"""
pdf2md — backward-compatibility shim.
All logic has moved to the core/ package. Import from there directly,
or just run  main.py  as the entry point.
"""
from core import convert, compress_md_file, estimate_pdf_tokens, count_tokens
from core.extractor import Item
from core.renderer import render_markdown, table_to_md
from core.compressor import compress_text
from core.vision import ImageBrain, squeeze

__all__ = [
    "convert",
    "compress_md_file",
    "estimate_pdf_tokens",
    "count_tokens",
    "Item",
    "render_markdown",
    "table_to_md",
    "compress_text",
    "ImageBrain",

    "squeeze",
]
