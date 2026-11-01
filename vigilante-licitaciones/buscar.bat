@echo off
REM Lo ejecuta la tarea programada cada dia: busca a diario en temporada (feb-sep)
REM y una vez por semana el resto del ano. Tambien se puede abrir con doble clic.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
".venv\Scripts\python.exe" src\vigilante.py buscar --programada >> logs\tarea.log 2>&1
