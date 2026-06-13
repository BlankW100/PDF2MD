#!/usr/bin/env python3
"""
PDFtoMD — entry point.

  No arguments  →  open GUI (same as double-clicking PDF to MD.bat)
  With PDF args →  CLI conversion (e.g. main.py report.pdf --compress aggressive)
"""
from __future__ import annotations
import sys


def run_gui():
    from gui.app import main
    main()


def run_cli():
    import argparse
    import glob
    import os
    from argparse import Namespace
    from core import convert
    from core.compressor import count_tokens

    p = argparse.ArgumentParser(
        description="Convert PDF(s) to token-efficient Markdown.")
    p.add_argument("pdf", nargs="+", help="PDF file(s); globs allowed")
    p.add_argument("-o", "--output", help="output .md path (single input only)")
    p.add_argument("--images", choices=["extract", "off", "ocr", "describe"],
                   default="extract")
    p.add_argument("--ocr-engine", choices=["auto", "rapidocr", "tesseract"],
                   default="auto")
    p.add_argument("--model", default="claude-sonnet-4-6",
                   help="Claude model for --images describe")
    p.add_argument("--dpi", type=int, default=200)
    p.add_argument("--compress", choices=["off", "balanced", "aggressive"],
                   default="balanced")
    p.add_argument("--no-title", dest="title", action="store_false")
    p.add_argument("--no-page-marks", dest="page_marks", action="store_false")
    p.add_argument("--no-popup", dest="popup", action="store_false")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    files: list[str] = []
    for pat in args.pdf:
        files.extend(glob.glob(pat) or [pat])
    files = [f for f in files if f.lower().endswith(".pdf")]
    if not files:
        sys.exit("No PDF files matched.")
    if args.output and len(files) > 1:
        sys.exit("-o/--output cannot be used with multiple inputs.")

    all_warnings: list[str] = []
    for f in files:
        if not os.path.exists(f):
            print(f"skip (not found): {f}", file=sys.stderr)
            continue
        try:
            out, warns, stats = convert(f, args)
            pdf_tok = stats.get("pdf_tokens", 0)
            md_tok = stats["tokens"]
            size_kb = os.path.getsize(out) / 1024
            print(f"{f} -> {out}")
            if stats.get("is_scanned"):
                print(f"  WARNING: scanned/image-only PDF (no text layer).")
                print(f"  Output: {md_tok:,} tokens | {size_kb:.1f} KB | {stats['elapsed']:.1f}s")
                if args.images == "extract":
                    print("  Re-run with --images ocr (offline) or --images describe (Claude AI)"
                          " to read the content inside the images.")
            else:
                pct = (1 - md_tok / pdf_tok) * 100 if pdf_tok else 0
                print(f"  PDF raw: ~{pdf_tok:,} tokens  ->  "
                      f"MD: {md_tok:,} tokens  "
                      f"({pct:.0f}% reduction | {size_kb:.1f} KB | {stats['elapsed']:.1f}s)")
            all_warnings += [f"{os.path.basename(f)} — {w}" for w in warns]
        except Exception as e:
            print(f"FAILED {f}: {e}", file=sys.stderr)

    if all_warnings:
        print(f"\n{len(all_warnings)} image(s)/page(s) had no readable text:")
        for w in all_warnings:
            print("  •", w)


if __name__ == "__main__":
    # First non-flag argument that ends in .pdf → CLI mode; otherwise → GUI
    non_flag_args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if non_flag_args:
        run_cli()
    else:
        run_gui()
