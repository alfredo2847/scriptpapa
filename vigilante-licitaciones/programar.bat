@echo off
REM Programa la busqueda diaria de licitaciones a las 08:40 (solo con la sesion de Windows iniciada).
REM Para quitarla: schtasks /Delete /TN "Vigilante licitaciones" /F
cd /d "%~dp0"
schtasks /Create /F /SC DAILY /ST 08:40 /TN "Vigilante licitaciones" /TR "\"%~dp0buscar.bat\"" || goto :error
echo.
echo Programado: cada dia a las 08:40. El resultado queda en datos\licitaciones.xlsx y logs\tarea.log
pause
goto :eof
:error
echo.
echo No se pudo programar. Copia el mensaje de arriba.
pause
exit /b 1
