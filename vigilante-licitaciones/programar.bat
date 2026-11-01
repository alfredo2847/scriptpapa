@echo off
REM Deja el vigilante funcionando solo:
REM  - tarea de Windows cada dia a las 08:40 (si el PC estaba apagado, se hace al encenderlo);
REM    en temporada (feb-sep) busca cada dia y el resto del ano una vez por semana;
REM  - acceso directo "Licitaciones de paellas" en el escritorio con la lista.
REM Para quitar la tarea: schtasks /Delete /TN "Vigilante licitaciones" /F
setlocal
cd /d "%~dp0"
set "BAT=%~dp0buscar.bat"
set "LISTA=%~dp0LISTA_LICITACIONES.html"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$a = New-ScheduledTaskAction -Execute '%BAT%';" ^
  "$t = New-ScheduledTaskTrigger -Daily -At '08:40';" ^
  "$s = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2);" ^
  "Register-ScheduledTask -TaskName 'Vigilante licitaciones' -Action $a -Trigger $t -Settings $s -Force | Out-Null" || goto :error
".venv\Scripts\python.exe" src\vigilante.py lista >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$w = New-Object -ComObject WScript.Shell;" ^
  "$l = $w.CreateShortcut([Environment]::GetFolderPath('Desktop') + '\Licitaciones de paellas.lnk');" ^
  "$l.TargetPath = '%LISTA%'; $l.Save()" || goto :error
echo.
echo Listo:
echo  - Se ejecuta solo cada dia a las 08:40 (si el PC esta apagado, al encenderlo).
echo    Febrero a septiembre: busca cada dia. Resto del ano: una vez por semana.
echo  - En el escritorio tienes "Licitaciones de paellas" con la lista.
echo  - Cuando salga una nueva, aparece un aviso de Windows.
pause
goto :eof
:error
echo.
echo No se pudo programar. Copia el mensaje de arriba.
pause
exit /b 1
