"""Tkinter GUI — two tabs: Convert PDF and Compress MD."""
from __future__ import annotations
import os
import queue
import sys
import threading
from argparse import Namespace

import tkinter as tk
from tkinter import filedialog, ttk

from core import convert, compress_md_file, estimate_pdf_tokens


_PAD = {"padx": 10, "pady": 5}


def _make_convert_opts(images: str, ocr_engine: str, compress: str) -> Namespace:
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
        root.geometry("620x580")
        root.resizable(True, True)

        self._log_q: queue.Queue[str] = queue.Queue()

        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=False, padx=8, pady=8)

        tab1 = tk.Frame(nb)
        nb.add(tab1, text="  Convert PDF  ")
        self._build_convert_tab(tab1)

        tab2 = tk.Frame(nb)
        nb.add(tab2, text="  Compress MD  ")
        self._build_compress_tab(tab2)

        # Shared output log
        log_frame = tk.LabelFrame(root, text="Output", padx=4, pady=4)
        log_frame.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        sb = tk.Scrollbar(log_frame)
        sb.pack(side="right", fill="y")
        self._log = tk.Text(log_frame, height=10, wrap="word",
                            font=("Consolas", 9), yscrollcommand=sb.set)
        self._log.pack(fill="both", expand=True)
        self._log.configure(state="disabled")
        sb.config(command=self._log.yview)

        root.after(100, self._drain_log)

    # ── Convert PDF tab ──────────────────────────────────────────────────────
    def _build_convert_tab(self, parent: tk.Frame):
        self._pdf_files: list[str] = []

        row = tk.Frame(parent)
        row.pack(fill="x", **_PAD)
        tk.Button(row, text="Choose PDF file(s)…", width=20,
                  command=self._pick_pdfs).pack(side="left")
        self._pdf_lbl = tk.Label(row, text="No files selected.",
                                 anchor="w", fg="#555", wraplength=360)
        self._pdf_lbl.pack(side="left", padx=8)

        # Custom output (single file only)
        tk.Label(parent, text="Output (single file only):",
                 font=("", 9, "bold")).pack(anchor="w", padx=10, pady=(8, 2))
        row_out = tk.Frame(parent)
        row_out.pack(anchor="w", padx=10, pady=2)
        tk.Label(row_out, text="Folder:").pack(side="left")
        self._out_folder = tk.StringVar()
        tk.Entry(row_out, textvariable=self._out_folder, width=34).pack(side="left", padx=4)
        tk.Button(row_out, text="Browse…", width=8,
                  command=self._pick_out_folder).pack(side="left")
        row_name = tk.Frame(parent)
        row_name.pack(anchor="w", padx=10, pady=2)
        tk.Label(row_name, text="Filename:").pack(side="left")
        self._out_name = tk.StringVar()
        tk.Entry(row_name, textvariable=self._out_name, width=34).pack(side="left", padx=4)
        tk.Label(row_name, text=".md", fg="#555").pack(side="left")

        # Settings
        tk.Label(parent, text="Settings:",
                 font=("", 9, "bold")).pack(anchor="w", padx=10, pady=(8, 2))
        row_s = tk.Frame(parent)
        row_s.pack(anchor="w", padx=10, pady=2)

        tk.Label(row_s, text="Images:").pack(side="left")
        self._images = tk.StringVar(value="extract")
        ttk.Combobox(row_s, textvariable=self._images, width=10, state="readonly",
                     values=["extract", "off", "ocr", "describe"]).pack(side="left", padx=(4, 12))

        tk.Label(row_s, text="OCR engine:").pack(side="left")
        self._engine = tk.StringVar(value="auto")
        ttk.Combobox(row_s, textvariable=self._engine, width=10, state="readonly",
                     values=["auto", "rapidocr", "tesseract"]).pack(side="left", padx=(4, 12))

        tk.Label(row_s, text="Compression:").pack(side="left")
        self._compress = tk.StringVar(value="balanced")
        ttk.Combobox(row_s, textvariable=self._compress, width=10, state="readonly",
                     values=["off", "balanced", "aggressive"]).pack(side="left", padx=4)

        tk.Label(parent,
                 text="Images: extract=save&link | off=ignore | ocr=offline text | describe=Claude AI\n"
                      "Compression: off | balanced=whitespace | aggressive=remove filler words",
                 fg="#777", font=("", 8), justify="left").pack(anchor="w", padx=10)

        self._convert_btn = tk.Button(parent, text="Convert", width=14,
                                      command=self._run_convert)
        self._convert_btn.pack(anchor="w", padx=10, pady=8)

    # ── Compress MD tab ──────────────────────────────────────────────────────
    def _build_compress_tab(self, parent: tk.Frame):
        self._md_file: str = ""

        tk.Label(parent,
                 text="Pick an existing Markdown file. The compressor reduces token\n"
                      "usage algorithmically — no AI, no API key needed.",
                 justify="left", fg="#444").pack(anchor="w", **_PAD)

        row = tk.Frame(parent)
        row.pack(fill="x", **_PAD)
        tk.Button(row, text="Choose .md file…", width=20,
                  command=self._pick_md).pack(side="left")
        self._md_lbl = tk.Label(row, text="No file selected.",
                                anchor="w", fg="#555", wraplength=340)
        self._md_lbl.pack(side="left", padx=8)

        row_m = tk.Frame(parent)
        row_m.pack(anchor="w", **_PAD)
        tk.Label(row_m, text="Mode:").pack(side="left")
        self._md_compress = tk.StringVar(value="balanced")
        ttk.Combobox(row_m, textvariable=self._md_compress, width=12, state="readonly",
                     values=["balanced", "aggressive"]).pack(side="left", padx=4)

        tk.Label(parent,
                 text="balanced    — remove page markers, collapse whitespace\n"
                      "aggressive — all of balanced + strip filler words from body text\n"
                      "             (headings, tables, and code blocks are never changed)",
                 fg="#777", font=("", 8), justify="left").pack(anchor="w", padx=10)

        self._compress_btn = tk.Button(parent, text="Compress", width=14,
                                       command=self._run_compress)
        self._compress_btn.pack(anchor="w", padx=10, pady=8)

    # ── Log helpers ──────────────────────────────────────────────────────────
    def _write(self, msg: str):
        self._log_q.put(msg)

    def _drain_log(self):
        while not self._log_q.empty():
            msg = self._log_q.get()
            self._log.configure(state="normal")
            self._log.insert("end", msg + "\n")
            self._log.see("end")
            self._log.configure(state="disabled")
        self.root.after(100, self._drain_log)

    # ── File pickers ─────────────────────────────────────────────────────────
    def _pick_pdfs(self):
        picked = filedialog.askopenfilenames(
            title="Choose PDF file(s)",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")])
        if picked:
            self._pdf_files = list(picked)
            names = ", ".join(os.path.basename(f) for f in self._pdf_files)
            self._pdf_lbl.config(text=f"{len(self._pdf_files)} file(s): {names}")
            self._out_folder.set("")
            self._out_name.set("")

    def _pick_out_folder(self):
        folder = filedialog.askdirectory(title="Choose output folder")
        if folder:
            self._out_folder.set(folder)

    def _pick_md(self):
        picked = filedialog.askopenfilename(
            title="Choose Markdown file",
            filetypes=[("Markdown files", "*.md"), ("All files", "*.*")])
        if picked:
            self._md_file = picked
            self._md_lbl.config(text=os.path.basename(picked))

    # ── Convert worker ────────────────────────────────────────────────────────
    def _run_convert(self):
        if not self._pdf_files:
            self._write("Pick at least one PDF first.")
            return
        self._convert_btn.config(state="disabled", text="Converting…")
        opts = _make_convert_opts(self._images.get(), self._engine.get(), self._compress.get())
        threading.Thread(target=self._work_convert, args=(opts,), daemon=True).start()

    def _work_convert(self, opts: Namespace):
        all_warnings: list[str] = []
        use_custom = len(self._pdf_files) == 1 and self._out_folder.get()

        for f in self._pdf_files:
            try:
                if use_custom:
                    folder = self._out_folder.get()
                    name = (self._out_name.get()
                            or os.path.splitext(os.path.basename(f))[0])
                    opts.output = os.path.join(folder, name + ".md")
                else:
                    opts.output = None

                out, warns, stats = convert(f, opts)

                pdf_tok = stats.get("pdf_tokens", 0)
                md_tok = stats["tokens"]
                size_kb = os.path.getsize(out) / 1024
                is_scanned = stats.get("is_scanned", False)

                self._write(f"✓ {os.path.basename(f)}  →  {os.path.basename(out)}")

                if is_scanned:
                    self._write(
                        f"  ⚠ Scanned / image-only PDF (no text layer found)."
                    )
                    self._write(
                        f"  Output: {md_tok:,} tokens | {size_kb:.1f} KB | {stats['elapsed']:.1f}s"
                    )
                    if opts.images == "extract":
                        self._write(
                            "  The content is inside the images — switch Images to  ocr  "
                            "(offline) or  describe  (Claude AI) to actually read it."
                        )
                else:
                    pct = (1 - md_tok / pdf_tok) * 100 if pdf_tok else 0
                    self._write(
                        f"  PDF raw: ~{pdf_tok:,} tokens  →  "
                        f"MD: {md_tok:,} tokens  "
                        f"({pct:.0f}% reduction | {size_kb:.1f} KB | {stats['elapsed']:.1f}s)"
                    )
                all_warnings += [f"{os.path.basename(f)} — {w}" for w in warns]
            except Exception as e:
                self._write(f"✗ {os.path.basename(f)}  FAILED: {e}")

        self._write("Done.")
        if all_warnings:
            self._write(f"\n⚠ {len(all_warnings)} image(s)/page(s) had no readable text:")
            for w in all_warnings:
                self._write("   • " + w)
            self._write("(For photos/charts, re-run with Images = describe.)")

        self.root.after(0, lambda: self._convert_btn.config(state="normal", text="Convert"))

    # ── Compress worker ───────────────────────────────────────────────────────
    def _run_compress(self):
        if not self._md_file:
            self._write("Pick a .md file first.")
            return
        self._compress_btn.config(state="disabled", text="Compressing…")
        threading.Thread(
            target=self._work_compress,
            args=(self._md_compress.get(),),
            daemon=True,
        ).start()

    def _work_compress(self, mode: str):
        try:
            out, before, after = compress_md_file(self._md_file, mode)
            saved = before["tokens"] - after["tokens"]
            pct = saved / before["tokens"] * 100 if before["tokens"] else 0
            self._write(f"✓ {os.path.basename(self._md_file)}  →  {os.path.basename(out)}")
            self._write(f"  Before : {before['tokens']:,} tokens  ({before['chars']:,} chars)")
            self._write(f"  After  : {after['tokens']:,} tokens  ({after['chars']:,} chars)")
            self._write(f"  Saved  : {saved:,} tokens  ({pct:.1f}% reduction)")
        except Exception as e:
            self._write(f"✗ FAILED: {e}")
        self.root.after(0, lambda: self._compress_btn.config(state="normal", text="Compress"))


def main():
    try:
        root = tk.Tk()
    except Exception as e:
        sys.exit(f"Could not open a window (no display?): {e}")
    App(root)
    root.mainloop()
