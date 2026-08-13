@echo off
chcp 65001 >nul
cd /d "%~dp0"
title Prospectador

if not exist ".venv\Scripts\python.exe" (
  echo.
  echo   Ambiente virtual nao encontrado.
  echo   Rode primeiro:  python -m venv .venv
  echo.
  pause
  exit /b 1
)

".venv\Scripts\python.exe" -m webapp
pause
