@echo off
setlocal
cd /d "%~dp0backend"
"C:\Program Files\Python310\python.exe" -m streamlit run streamlit_app.py
endlocal
