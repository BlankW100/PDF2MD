# PDFtoMD

A PDF → Markdown converter optimised for LLM/AI token efficiency.
Pulls **text, headings, tables, and images** out of any PDF and writes clean,
compressed Markdown — plus an algorithmic compressor that shrinks existing `.md` files
without any AI or API.

---

## Download (no Python needed)

**[⬇ Download PDFtoMD.exe](https://github.com/BlankW100/PDF2MD/releases/latest/download/PDFtoMD.exe)**

Windows only · single file · just download and double-click.

Or see all releases: [github.com/BlankW100/PDF2MD/releases](https://github.com/BlankW100/PDF2MD/releases)

---

## What it does

- **Text** — collapses messy PDF whitespace into tidy paragraphs.
- **Headings** — inferred from font sizes (`#`/`##`/`###`…), so document structure survives.
- **Tables** — detected and rendered as real Markdown tables.
- **Images** — extracted & linked by default, or turned into text via OCR / Claude vision.
- **Noise removal** — strips repeated running headers/footers and bare page numbers.
- **Scanned PDFs** — pages with no text layer are rendered and sent to OCR/vision.
- **Token counter** — shows exact token count of output (PDF raw vs MD output).
- **MD Compressor** — algorithmically compresses any existing `.md` file (no AI needed).

---

## GUI workflow

### Tab 1 — Convert PDF
1. Click **Choose PDF file(s)…** and pick one or more PDFs.
2. *(Optional)* Set an output folder/filename for single-file runs.
3. Choose **Images**, **OCR engine**, and **Compression** settings.
4. Click **Convert**.
5. The log shows: `PDF raw: ~8,234 tokens → MD: 3,421 tokens (58% reduction | 1.2 KB | 12s)`

### Tab 2 — Compress MD
1. Click **Choose .md file…** and pick an existing Markdown file.
2. Choose **balanced** or **aggressive** mode.
3. Click **Compress** — saves a `_compressed.md` next to the original.
4. The log shows before/after token counts and the savings percentage.

---

## Image handling (`--images`)

| Mode | Needs | Result |
|------|-------|--------|
| `extract` *(default)* | nothing | saves images to `<name>_assets/`, links them |
| `off` | nothing | ignores images entirely |
| `ocr` | local OCR engine (see below) | reads text from images — **fully offline, no API** |
| `describe` | `anthropic` + `ANTHROPIC_API_KEY` | Claude vision describes images & scanned pages |

## Compression modes

| Mode | What it removes |
|------|----------------|
| `off` | nothing |
| `balanced` *(default)* | extra whitespace, page marker comments |
| `aggressive` | all of balanced + ~30 filler words (`the`, `a`, `and`, `is`…) from body text |

Headings, tables, and code blocks are never modified.

---

## Install from source (Python)

```powershell
pip install -r requirements.txt
python main.py          # opens GUI
python main.py report.pdf               # CLI: convert one file
python main.py *.pdf --compress aggressive   # batch with aggressive compression
```

### OCR engines for `--images ocr` (offline, no API)

- **RapidOCR** — `pip install rapidocr-onnxruntime` — pip-only, easiest.
- **Tesseract** — `pip install pytesseract pillow` + install the Tesseract binary.

### Claude vision for `--images describe`

```powershell
pip install anthropic
set ANTHROPIC_API_KEY=sk-ant-...
python main.py scan.pdf --images describe
```

---

## Build EXE yourself

```powershell
pip install pyinstaller
build.bat
# → dist\PDFtoMD.exe
```

---

## Notes

- All conversion is fully offline. Only `--images describe` makes network calls.
- Heading detection is font-size based; very stylised PDFs may need tuning of the `1.15` ratio in `core/extractor.py`.
- `tiktoken` is optional — if not installed, token counts are estimated at `chars ÷ 4`.
