@echo off
REM Actualiza SOLO esta carpeta desde GitHub. No toca .venv, datos, logs ni config.yaml,
REM y no toca nada del bot de registro.
setlocal
cd /d "%~dp0"
set "URL=https://github.com/alfredo2847/scriptpapa/archive/refs/heads/claude/confident-lamport-7e55jw.zip"
set "ZIP=%TEMP%\vigilante_actualizacion.zip"
set "DIR=%TEMP%\vigilante_actualizacion"
echo Descargando la ultima version del vigilante...
powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing -Uri '%URL%' -OutFile '%ZIP%'" || goto :error
if exist "%DIR%" rmdir /s /q "%DIR%"
powershell -NoProfile -Command "Expand-Archive -Path '%ZIP%' -DestinationPath '%DIR%' -Force" || goto :error
set "SRC="
for /d %%D in ("%DIR%\scriptpapa-*") do set "SRC=%%D\vigilante-licitaciones"
if not exist "%SRC%\src\vigilante.py" goto :error
robocopy "%SRC%" "%CD%" /E /XD .venv datos logs /XF config.yaml /NFL /NDL /NJH /NJS /NP
if %ERRORLEVEL% GEQ 8 goto :error
.venv\Scripts\pip install -q -r requirements.txt
echo.
echo Vigilante actualizado.
pause
goto :eof
:error
echo.
echo Error al actualizar. Copia el mensaje de arriba.
pause
exit /b 1
