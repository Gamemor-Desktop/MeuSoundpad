@echo off
cd /d "%~dp0"
echo Instalando dependencias e o PyInstaller...
python -m pip install -r requirements.txt pyinstaller --quiet --disable-pip-version-check
if errorlevel 1 (
    echo Falha ao instalar as dependencias.
    pause
    exit /b 1
)
python -m PyInstaller --noconfirm --onefile --noconsole --name MeuSoundpad ^
    --collect-all tkinterdnd2 soundpad.py
if errorlevel 1 (
    echo Falha ao gerar o executavel.
    pause
    exit /b 1
)
echo.
echo Pronto: dist\MeuSoundpad.exe
pause
