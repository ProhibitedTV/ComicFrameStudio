@echo off
setlocal
title ComicFrame Studio 2.0
cd /d "%~dp0"

py -c "import requests, PIL, numpy, cv2" >nul 2>&1
if errorlevel 1 (
    echo ComicFrame dependencies are missing or changed. Installing requirements...
    py -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo Dependency installation failed.
        pause
        exit /b 1
    )
)

py app.py
if errorlevel 1 (
    echo.
    echo ComicFrame Studio exited with an error.
    pause
)
endlocal
