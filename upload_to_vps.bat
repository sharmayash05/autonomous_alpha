@echo off
setlocal

echo ==========================================
echo   Upload to Vultr VPS
echo ==========================================

set /p VPS_IP="Enter your VPS IP Address: "
set /p VPS_USER="Enter VPS Username (usually root): "

echo.
echo [INFO] Preparing to upload files to %VPS_USER%@%VPS_IP%...
echo.

REM Create a temporary directory for clean upload
if not exist "dist" mkdir dist
copy Dockerfile dist\ >nul
copy docker-compose.yml dist\ >nul
copy requirements.txt dist\ >nul
copy setup.sh dist\ >nul
copy .env dist\ >nul 2>&1
xcopy /E /I /Y src dist\src >nul
xcopy /E /I /Y config dist\config >nul
xcopy /E /I /Y prompts dist\prompts >nul
xcopy /E /I /Y monitoring dist\monitoring >nul

echo [INFO] Uploading files...
scp -r dist/* %VPS_USER%@%VPS_IP%:/root/autonomous-alpha/

echo.
if %ERRORLEVEL% EQU 0 (
    echo [SUCCESS] Upload complete!
    echo.
    echo Next steps:
    echo 1. SSH into your server: ssh %VPS_USER%@%VPS_IP%
    echo 2. Go to the directory: cd autonomous-alpha
    echo 3. Run setup: chmod +x setup.sh && ./setup.sh
    echo 4. Start agent: docker-compose up -d
) else (
    echo [ERROR] Upload failed. Please check your IP and SSH access.
)

REM Cleanup
rd /s /q dist

pause
