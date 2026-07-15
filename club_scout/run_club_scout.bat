@echo off
REM Club Scout（広尾一口選定）単独起動 — 馬券予想とは非連携
cd /d "%~dp0"
set PYTHON=C:\Users\youmz\AppData\Local\Programs\Python\Python312\python.exe
"%PYTHON%" -c "import streamlit" 2>nul
if errorlevel 1 (
  echo streamlit が未導入です。次を実行してください:
  echo   "%PYTHON%" -m pip install streamlit pyyaml
  pause
  exit /b 1
)
"%PYTHON%" -m streamlit run app.py
