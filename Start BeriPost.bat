@echo off
REM Double-click this file to open the BeriPost desktop app.
REM It runs the app using the project's own Python (.venv).
cd /d "%~dp0"
".venv\Scripts\python.exe" gui.py
