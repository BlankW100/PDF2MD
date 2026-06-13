@echo off
rem ==== PDF to MD — double-click launcher ====
rem Runs the GUI with no console window, from this file's folder.
cd /d "%~dp0"

where pythonw >nul 2>nul && (start "" pythonw "main.py" & exit /b)
where pyw     >nul 2>nul && (start "" pyw     "main.py" & exit /b)
where python  >nul 2>nul && (start "" python  "main.py" & exit /b)

echo Python was not found on this PC.
echo Install it from https://www.python.org/downloads/  (tick "Add to PATH"),
echo then run:  pip install -r requirements.txt
pause
