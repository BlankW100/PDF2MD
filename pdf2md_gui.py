#!/usr/bin/env python3
"""
pdf2md_gui — GUI front-end for pdf2md.py with two workflows:
  Tab 1 "Convert PDF"  — pick PDF(s), choose settings, convert to Markdown.
                         Shows raw PDF token estimate vs final MD token count.
  Tab 2 "Compress MD"  — pick an existing .md file, compress algorithmically,
                         show before/after token savings.
"""
from __future__ import annotations

import os
import queue
import sys
import threading
from argparse import Namespace

import tkinter as tk
from tkinter import filedialog, ttk

import pdf2md


PAD = {"padx": 10, "pady": 5}


def make_convert_opts(images: str, ocr_engine: str, compress: str) -> Namespace:
    return Namespace(
        output=None,
        images=images,
        ocr_engine=ocr_engine,
        model="claude-sonnet-4-6",
        dpi=200,
        compress=compress,
        title=True,
        page_marks=True,
        popup=False,
        verbose=False,
    )


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("PDF → Markdown")
        root.geometry("600x560")
        root.resizable(True, True)

        self.log_q: queue.Queue[str] = queue.Queue()

        notebook = ttk.Notebook(root)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)

        # ── Tab 1: Convert PDF ──────────────────────────────────────────────
        tab_convert = tk.Frame(notebook)
        notebook.add(tab_convert, text="  Convert PDF  ")
        self._build_convert_tab(tab_convert)

        # ── Tab 2: Compress MD ──────────────────────────────────────────────
        tab_compress = tk.Frame(notebook)
        notebook.add(tab_compress, text="  Compress MD  ")
        self._build_compress_tab(tab_compress)

        # ── Shared log ──────────────────────────────────────────────────────
        log_frame = tk.Frame(root)
        log_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        tk.Label(log_frame, text="Output", anchor="w", font=("", 9, "bold")).pack(anchor="w")
        self.log = tk.Text(log_frame, height=10, wrap="word", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True)
        self.log.configure(state="disabled")

        self.root.after(100, self._drain_log)

    # ── Convert tab ─────────────────────────────────────────────────────────
    def _build_convert_tab(self, parent: tk.Frame):
        self.pdf_files: list[str] = []

        # File picker
        row = tk.Frame(parent)
        row.pack(fill="x", **PAD)
        tk.Button(row, text="Choose PDF file(s)…", width=20,
                  command=self._pick_pdfs).pack(side="left")
        self.pdf_lbl = tk.Label(row, text="No files selected.", anchor="w",
                                fg="#555", wraplength=360)
        self.pdf_lbl.pack(side="left", padx=8)

        # Output location (single file only)
        tk.Label(parent, text="Output (single file only):",
                 font=("", 9, "bold")).pack(anchor="w", padx=10, pady=(6, 2))
        row_out = tk.Frame(parent)
        row_out.pack(anchor="w", padx=10, pady=2)
        tk.Label(row_out, text="Folder:").pack(side="left")
        self.out_folder = tk.StringVar()
        tk.Entry(row_out, textvariable=self.out_folder, width=32).pack(side="left", padx=4)
        tk.Button(row_out, text="Browse…", width=8,
                  command=self._pick_out_folder).pack(side="left")
        row_name = tk.Frame(parent)
        row_name.pack(anchor="w", padx=10, pady=2)
        tk.Label(row_name, text="Filename:").pack(side="left")
        self.out_name = tk.StringVar()
        tk.Entry(row_name, textvariable=self.out_name, width=32).pack(side="left", padx=4)
        tk.Label(row_name, text=".md", fg="#555").pack(side="left")

        # Settings row
        tk.Label(parent, text="Settings:", font=("", 9, "bold")).pack(
            anchor="w", padx=10, pady=(8, 2))
        row_s = tk.Frame(parent)
        row_s.pack(anchor="w", padx=10, pady=2)

        tk.Label(row_s, text="Images:").pack(side="left")
        self.images = tk.StringVar(value="extract")
        ttk.Combobox(row_s, textvariable=self.images, width=10, state="readonly",
                     values=["extract", "off", "ocr", "describe"]).pack(side="left", padx=(4, 14))

        tk.Label(row_s, text="OCR engine:").pack(side="left")
        self.engine = tk.StringVar(value="auto")
        ttk.Combobox(row_s, textvariable=self.engine, width=10, state="readonly",
                     values=["auto", "rapidocr", "tesseract"]).pack(side="left", padx=(4, 14))

        tk.Label(row_s, text="Compression:").pack(side="left")
        self.compress = tk.StringVar(value="balanced")
        ttk.Combobox(row_s, textvariable=self.compress, width=10, state="readonly",
                     values=["off", "balanced", "aggressive"]).pack(side="left", padx=4)

        tk.Label(parent,
                 text="Images: extract=save & link | off=ignore | ocr=offline text | describe=Claude AI\n"
                      "Compression: off=none | balanced=whitespace only | aggressive=remove filler words",
                 fg="#777", font=("", 8), justify="left").pack(anchor="w", padx=10)

        # Convert button
        self.convert_btn = tk.Button(parent, text="Convert", width=14,
                                     command=self._run_convert)
        self.convert_btn.pack(anchor="w", **PAD)

    # ── Compress tab ────────────────────────────────────────────────────────
    def _build_compress_tab(self, parent: tk.Frame):
        self.md_file: str = ""

        tk.Label(parent,
                 text="Pick an existing Markdown file and compress its token usage\n"
                      "algorithmically — no AI, no API key needed.",
                 justify="left", fg="#444").pack(anchor="w", **PAD)

        # File picker
        row = tk.Frame(parent)
        row.pack(fill="x", **PAD)
        tk.Button(row, text="Choose .md file…", width=20,
                  command=self._pick_md).pack(side="left")
        self.md_lbl = tk.Label(row, text="No file selected.", anchor="w",
                               fg="#555", wraplength=340)
        self.md_lbl.pack(side="left", padx=8)

        # Mode
        row_m = tk.Frame(parent)
        row_m.pack(anchor="w", **PAD)
        tk.Label(row_m, text="Mode:").pack(side="left")
        self.md_compress = tk.StringVar(value="balanced")
        ttk.Combobox(row_m, textvariable=self.md_compress, width=12, state="readonly",
                     values=["balanced", "aggressive"]).pack(side="left", padx=4)

        tk.Label(parent,
                 text="balanced    — strip page comments, collapse whitespace\n"
                      "aggressive — also remove filler words (the, a, and, is, …)",
                 fg="#777", font=("", 8), justify="left").pack(anchor="w", padx=10)

        # What each mode does
        info = (
            "\nWhat gets removed:\n"
            "  balanced:    <!-- page N --> markers, trailing spaces, extra blank lines,\n"
            "               repeated whitespace inside lines\n"
            "  aggressive:  all of the above + ~30 common filler/function words\n"
            "               (articles, conjunctions, auxiliary verbs) from body text\n"
            "               Headings, tables, and code blocks are never touched."
        )
        tk.Label(parent, text=info, fg="#555", font=("Consolas", 8),
                 justify="left", anchor="w").pack(anchor="w", padx=10, pady=(4, 0))

        self.compress_btn = tk.Button(parent, text="Compress", width=14,
                                      command=self._run_compress)
        self.compress_btn.pack(anchor="w", **PAD)

    # ── Helpers ─────────────────────────────────────────────────────────────
    def _write(self, msg: str):
        self.log_q.put(msg)

    def _drain_log(self):
        while not self.log_q.empty():
            msg = self.log_q.get()
            self.log.configure(state="normal")
            self.log.insert("end", msg + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")
        self.root.after(100, self._drain_log)

    def _pick_pdfs(self):
        picked = filedialog.askopenfilenames(
            title="Choose PDF file(s)",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")])
        if picked:
            self.pdf_files = list(picked)
            names = ", ".join(os.path.basename(f) for f in self.pdf_files)
            self.pdf_lbl.config(text=f"{len(self.pdf_files)} file(s): {names}")
            self.out_folder.set("")
            self.out_name.set("")

    def _pick_out_folder(self):
        folder = filedialog.askdirectory(title="Choose output folder")
        if folder:
            self.out_folder.set(folder)

    def _pick_md(self):
        picked = filedialog.askopenfilename(
            title="Choose Markdown file",
            filetypes=[("Markdown files", "*.md"), ("All files", "*.*")])
        if picked:
            self.md_file = picked
            self.md_lbl.config(text=os.path.basename(picked))

    # ── Convert worker ──────────────────────────────────────────────────────
    def _run_convert(self):
        if not self.pdf_files:
            self._write("Pick at least one PDF first.")
            return
        self.convert_btn.config(state="disabled", text="Converting…")
        opts = make_convert_opts(self.images.get(), self.engine.get(), self.compress.get())
        threading.Thread(target=self._work_convert, args=(opts,), daemon=True).start()

    def _work_convert(self, opts: Namespace):
        all_warnings: list[str] = []
        use_custom = len(self.pdf_files) == 1 and self.out_folder.get()

        for f in self.pdf_files:
            try:
                if use_custom:
                    folder = self.out_folder.get()
                    name = self.out_name.get() or os.path.splitext(os.path.basename(f))[0]
                    opts.output = os.path.join(folder, name + ".md")
                else:
                    opts.output = None

                out, warns, stats = pdf2md.convert(f, opts)

                pdf_tok = stats.get("pdf_tokens", 0)
                md_tok = stats["tokens"]
                reduction = (1 - md_tok / pdf_tok) * 100 if pdf_tok else 0
                size_kb = os.path.getsize(out) / 1024

                self._write(f"✓ {os.path.basename(f)}  →  {os.path.basename(out)}")
                self._write(
                    f"  PDF raw: ~{pdf_tok:,} tokens  →  MD: {md_tok:,} tokens"
                    f"  ({reduction:.0f}% reduction, {size_kb:.1f} KB, {stats['elapsed']:.1f}s)"
                )
                all_warnings += [f"{os.path.basename(f)} — {w}" for w in warns]
            except Exception as e:
                self._write(f"✗ {os.path.basename(f)}  FAILED: {e}")

        self._write("Done.")
        if all_warnings:
            self._write(f"\n⚠ {len(all_warnings)} image(s)/page(s) had no readable text:")
            for w in all_warnings:
                self._write("   • " + w)
            self._write("(For photos/charts, try Images = describe.)")

        self.root.after(0, lambda: self.convert_btn.config(state="normal", text="Convert"))

    # ── Compress worker ─────────────────────────────────────────────────────
    def _run_compress(self):
        if not self.md_file:
            self._write("Pick a .md file first.")
            return
        self.compress_btn.config(state="disabled", text="Compressing…")
        mode = self.md_compress.get()
        threading.Thread(target=self._work_compress, args=(mode,), daemon=True).start()

    def _work_compress(self, mode: str):
        try:
            out, before, after = pdf2md.compress_md_file(self.md_file, mode)
            saved = before["tokens"] - after["tokens"]
            pct = saved / before["tokens"] * 100 if before["tokens"] else 0
            self._write(f"✓ {os.path.basename(self.md_file)}  →  {os.path.basename(out)}")
            self._write(f"  Before: {before['tokens']:,} tokens  ({before['chars']:,} chars)")
            self._write(f"  After:  {after['tokens']:,} tokens  ({after['chars']:,} chars)")
            self._write(f"  Saved:  {saved:,} tokens  ({pct:.1f}% reduction)")
        except Exception as e:
            self._write(f"✗ FAILED: {e}")

        self.root.after(0, lambda: self.compress_btn.config(state="normal", text="Compress"))


def main():
    try:
        root = tk.Tk()
    except Exception as e:
        sys.exit(f"Could not open a window (no display?): {e}")
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
