@echo off
REM Baut FotoRahmen.exe (eine einzelne Datei) im Ordner dist\
REM Voraussetzung: Python 3.12 oder neuer von python.org (bei der Installation "Add to PATH" anhaken)
cd /d "%~dp0"

python -m pip install --upgrade pip || goto :fehler
python -m pip install -r requirements.txt pyinstaller || goto :fehler
python selftest.py || goto :fehler

python -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name FotoRahmen ^
  --icon assets\icon.ico ^
  --add-data "assets\icon.png;assets" ^
  --collect-all pillow_heif ^
  --collect-submodules imagecodecs ^
  fotorahmen.py || goto :fehler

echo.
echo Fertig: dist\FotoRahmen.exe
pause
exit /b 0

:fehler
echo.
echo Beim Bauen ist ein Fehler aufgetreten.
pause
exit /b 1
