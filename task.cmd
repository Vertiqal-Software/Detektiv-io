:: task.cmd  (repo root, optional for cmd.exe or double-click)
@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%task.ps1" %*
endlocal