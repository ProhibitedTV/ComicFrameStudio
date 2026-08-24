@echo off
title ComicFrame Studio
cd /d "%~dp0"
py app.py
if errorlevel 1 (
    echo.
    echo ComicFrame Studio exited with an error.
    pause
)
