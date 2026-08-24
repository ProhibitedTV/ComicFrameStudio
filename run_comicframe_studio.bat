@echo off
title ComicFrame Studio 1.2
cd /d "%~dp0"
py comicframe_studio_v1_1.py
if errorlevel 1 (
    echo.
    echo ComicFrame Studio exited with an error.
    pause
)
