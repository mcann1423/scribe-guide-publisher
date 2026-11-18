@echo off
cd /d "%~dp0"
py -3 app.py
if errorlevel 1 (
  echo.
  echo Could not start the publisher. Install Python 3.10 or later with tkinter from python.org.
  pause
)
