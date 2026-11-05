@echo off
REM Launched by Windows Task Scheduler ("Longform" task).
REM Generates an original story, renders it, makes an AI thumbnail and uploads it.
REM Output appended to logs\pipeline.log
cd /d "%~dp0"
if not exist logs mkdir logs
set PYTHONIOENCODING=utf-8
venv\Scripts\python.exe main_longform_generated.py >> logs\pipeline.log 2>&1
