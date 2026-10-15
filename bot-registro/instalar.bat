@echo off
REM Instala el entorno del bot (Python 3.12+ y Google Chrome ya instalados)
py -3 -m venv .venv || goto :error
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt || goto :error
echo.
echo Listo. Activa el entorno con: .venv\Scripts\activate
goto :eof
:error
echo Error en la instalacion.
exit /b 1
