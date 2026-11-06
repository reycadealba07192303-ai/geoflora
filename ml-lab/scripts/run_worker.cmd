@echo off
rem Started by the Windows task "GeoFlora training worker" at logon (see docs/HANDOVER-GeoFlora-2026-11-07.md).
cd /d "%~dp0.."
".venv\Scripts\python.exe" -u scripts\app_training_worker.py >> "..\storage\logs\app-training-worker.log" 2>&1
