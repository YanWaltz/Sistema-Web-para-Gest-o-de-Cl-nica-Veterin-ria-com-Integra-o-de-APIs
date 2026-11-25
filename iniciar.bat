@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  where py >nul 2>nul
  if not errorlevel 1 (
    py -3 -m venv .venv
  ) else (
    python -m venv .venv
  )
)
if not exist ".venv\Scripts\python.exe" goto erro
if not exist ".venv\sdm-deps-ok" (
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  if errorlevel 1 goto erro
  type nul > ".venv\sdm-deps-ok"
)
".venv\Scripts\python.exe" iniciar.py
if errorlevel 1 goto erro
exit /b 0
:erro
echo Nao foi possivel iniciar. Instale Python 3.10 ou superior e veja a mensagem acima.
pause
exit /b 1
