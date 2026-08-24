@echo off
title ComicFrame Studio 1.3
cd /d "%~dp0"
py comicframe_studio_v1_3.py
if errorlevel 1 (
    echo.
    echo ComicFrame Studio exited with an error.
    pause
)
