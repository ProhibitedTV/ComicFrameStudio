@echo off
title ComicFrame Studio
cd /d "%~dp0"
py comicframe_studio.py
if errorlevel 1 (
    echo.
    echo ComicFrame Studio exited with an error.
    pause
)
