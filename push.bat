@echo off
set PATH=C:\Users\Administrator\.workbuddy\vendor\PortableGit\mingw64\bin;%PATH%
cd /d "C:\Users\Administrator\WorkBuddy\2026-06-17-18-15-04\spherical-memory-mcp"
set GIT_SSL_NO_VERIFY=1
git push origin main
echo.
echo === Done ===
pause
