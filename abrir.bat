@echo off
cd /d "%~dp0"
echo Verificando bibliotecas (so demora na primeira vez)...
python -m pip install -r requirements.txt --quiet --disable-pip-version-check
if errorlevel 1 (
    echo.
    echo Nao consegui instalar as bibliotecas. O Python esta instalado e no PATH?
    pause
    exit /b
)
python soundpad.py
if errorlevel 1 pause
