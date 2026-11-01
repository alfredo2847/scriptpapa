@echo off
REM Lo ejecuta la tarea programada cada dia. Tambien se puede abrir con doble clic.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" src\vigilante.py buscar >> logs\tarea.log 2>&1
