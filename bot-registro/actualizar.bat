@echo off
REM Actualiza el bot desde GitHub sin tocar .venv, datos, justificantes, capturas, logs ni perfil_chrome
setlocal
cd /d "%~dp0"
set "URL=https://github.com/alfredo2847/scriptpapa/archive/refs/heads/ccr-d693d3ab-zeheyf.zip"
set "ZIP=%TEMP%\bot_actualizacion.zip"
set "DIR=%TEMP%\bot_actualizacion"
echo Descargando la ultima version del bot...
powershell -NoProfile -Command "Invoke-WebRequest -UseBasicParsing -Uri '%URL%' -OutFile '%ZIP%'" || goto :error
if exist "%DIR%" rmdir /s /q "%DIR%"
powershell -NoProfile -Command "Expand-Archive -Path '%ZIP%' -DestinationPath '%DIR%' -Force" || goto :error
robocopy "%DIR%\scriptpapa-ccr-d693d3ab-zeheyf\bot-registro" "%CD%" /E /XD .venv datos justificantes capturas logs perfil_chrome /NFL /NDL /NJH /NJS /NP
if %ERRORLEVEL% GEQ 8 goto :error
echo.
echo Bot actualizado. Comprueba con: python src/main.py --help
pause
goto :eof
:error
echo.
echo Error al actualizar. Copia el mensaje de arriba.
pause
exit /b 1
