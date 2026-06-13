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
pyinstaller ^
  --onefile ^
  --windowed ^
  --name "PDFtoMD" ^
  --collect-all fitz ^
  --collect-data tiktoken ^
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
