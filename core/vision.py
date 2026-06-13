"""ImageBrain — OCR (offline) and Claude vision (online) backends."""
from __future__ import annotations
import base64
import re
import sys

try:
    import fitz
except ImportError:
    sys.exit("PyMuPDF is required: pip install PyMuPDF")

_WS = re.compile(r"[ \t ]+")
_MULTINL = re.compile(r"\n{3,}")


def squeeze(s: str) -> str:
    return _WS.sub(" ", s).strip()


def _to_png(data: bytes) -> bytes:
    """Best-effort convert arbitrary image bytes to PNG via PyMuPDF."""
    try:
        return fitz.Pixmap(data).tobytes("png")
    except Exception:
        return data


class ImageBrain:
    """Lazily-initialised OCR / vision helper. mode in {off, ocr, describe}."""

    def __init__(self, mode: str, model: str, ocr_engine: str = "auto"):
        self.mode = mode
        self.model = model
        self.ocr_engine = ocr_engine
        self._ocr = None
        self._client = None

    def _init_ocr(self):
        order = (["rapidocr", "tesseract"] if self.ocr_engine == "auto"
                 else [self.ocr_engine])
        errors = []
        for eng in order:
            try:
                if eng == "rapidocr":
                    from rapidocr_onnxruntime import RapidOCR
                    reader = RapidOCR()

                    def run(png, _r=reader):
                        import io
                        import numpy as np
                        from PIL import Image
                        arr = np.array(Image.open(io.BytesIO(png)).convert("RGB"))
                        res, _ = _r(arr)
                        return "\n".join(line[1] for line in res) if res else ""

                    self._ocr = ("rapidocr", run)
                    return
                if eng == "tesseract":
                    import io
                    import pytesseract
                    from PIL import Image
                    pytesseract.get_tesseract_version()

                    def run(png):
                        return pytesseract.image_to_string(Image.open(io.BytesIO(png)))

                    self._ocr = ("tesseract", run)
                    return
            except Exception as e:
                errors.append(f"{eng}: {e}")
        raise RuntimeError(
            "No local OCR engine found.\n"
            "  pip install rapidocr-onnxruntime\n"
            "  OR pip install pytesseract pillow + Tesseract binary\n"
            "Details: " + " | ".join(errors))

    def ocr(self, png: bytes) -> str:
        if self._ocr is None:
            self._init_ocr()
        txt = self._ocr[1](png)
        return _MULTINL.sub("\n\n", "\n".join(squeeze(l) for l in txt.splitlines())).strip()

    def describe(self, png: bytes, hint: str = "") -> str:
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()
        prompt = (
            "Convert this image into clean, token-efficient Markdown for an LLM to read. "
            "If it is a table, output a Markdown table. If it is a chart/diagram, give a short "
            "factual description plus any data labels. If it is a photo, describe it in one line. "
            "Transcribe any text verbatim. Output ONLY the Markdown, no preamble."
        )
        if hint:
            prompt += f"\nContext: {hint}"
        b64 = base64.standard_b64encode(png).decode()
        msg = self._client.messages.create(
            model=self.model,
            max_tokens=1500,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image",
                     "source": {"type": "base64", "media_type": "image/png", "data": b64}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        return "".join(b.text for b in msg.content if b.type == "text").strip()

    def process(self, png: bytes, hint: str = "") -> str:
        if self.mode == "ocr":
            return self.ocr(png)
        if self.mode == "describe":
            return self.describe(png, hint)
        return ""
