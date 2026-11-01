@echo off
REM Instala el entorno del vigilante (Python 3.12+ ya instalado). No toca el bot de registro.
cd /d "%~dp0"
py -3 -m venv .venv || goto :error
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt || goto :error
echo.
echo Listo. Prueba con: .venv\Scripts\python src\vigilante.py buscar
pause
goto :eof
:error
echo.
echo Error en la instalacion. Copia el mensaje de arriba.
pause
exit /b 1
