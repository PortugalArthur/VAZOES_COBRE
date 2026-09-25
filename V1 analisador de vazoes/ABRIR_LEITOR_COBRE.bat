@echo off
cd /d "%~dp0"
python leitor_parquet_vazoes_cobre.py
if errorlevel 1 pause
