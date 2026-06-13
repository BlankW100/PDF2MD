@echo off
rem ============================================================
rem  PDFtoMD — one-click EXE builder
rem  Requires: pip install pyinstaller  (run once before this)
rem  Output:   dist\PDFtoMD.exe
rem ============================================================
cd /d "%~dp0"

echo Installing / updating PyInstaller...
pip install pyinstaller --quiet

echo.
echo Building EXE...
rem Note: tiktoken is NOT included — its encoding cache files cannot be bundled
rem by PyInstaller. The app falls back to chars/4 token estimation automatically.
pyinstaller ^
  --onefile ^
  --windowed ^
  --name "PDFtoMD" ^
  --collect-all fitz ^
  --hidden-import anthropic ^
  --hidden-import rapidocr_onnxruntime ^
  --hidden-import pytesseract ^
  main.py

echo.
if exist "dist\PDFtoMD.exe" (
    echo  Build succeeded!
    echo  Your EXE is at:  dist\PDFtoMD.exe
    echo  Upload dist\PDFtoMD.exe to your GitHub Release.
) else (
    echo  Build FAILED — check the output above for errors.
)
echo.
pause
