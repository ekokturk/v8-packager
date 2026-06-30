@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "DOCKER_SCRIPT=%SCRIPT_DIR%docker\docker.py"
set "ORIGINAL_ENGINE="
set "BUILD_FAILED=0"
set "VERSION_ARGS="
set "LIBRARY_TYPE=Static"
if not "%~1"=="" set "VERSION_ARGS=--version %~1"
if not "%~2"=="" set "LIBRARY_TYPE=%~2"

if exist "%SCRIPT_DIR%archive" rmdir /s /q "%SCRIPT_DIR%archive"

where docker >nul 2>&1
if errorlevel 1 (
    echo Error: Docker CLI was not found.
    exit /b 1
)

where python >nul 2>&1
if errorlevel 1 (
    echo Error: Python was not found.
    exit /b 1
)

for /f "usebackq delims=" %%e in (`docker info --format "{{.OSType}}" 2^>nul`) do set "ORIGINAL_ENGINE=%%e"
if not defined ORIGINAL_ENGINE (
    echo Error: Docker Desktop is not running.
    exit /b 1
)

call :BuildPlatform windows windows
if errorlevel 1 set "BUILD_FAILED=1"

if "!BUILD_FAILED!"=="0" (
    call :BuildPlatform linux linux
    if errorlevel 1 set "BUILD_FAILED=1"
)

if "!BUILD_FAILED!"=="0" (
    call :BuildPlatform android linux
    if errorlevel 1 set "BUILD_FAILED=1"
)

if defined ORIGINAL_ENGINE (
    call :SwitchEngine "!ORIGINAL_ENGINE!"
    if errorlevel 1 (
        echo Warning: Could not restore the !ORIGINAL_ENGINE! Docker engine.
        set "BUILD_FAILED=1"
    )
)

if "!BUILD_FAILED!"=="1" (
    echo Docker build failed.
    exit /b 1
)

echo Windows, Linux, and Android Docker builds completed successfully.
exit /b 0


:BuildPlatform
set "PLATFORM=%~1"
set "ENGINE=%~2"
call :SwitchEngine "%ENGINE%"
if errorlevel 1 exit /b 1

python "%DOCKER_SCRIPT%" --image %ENGINE%
if errorlevel 1 exit /b 1

python "%DOCKER_SCRIPT%" --build %PLATFORM% --library-type !LIBRARY_TYPE! --archive !VERSION_ARGS!
if errorlevel 1 exit /b 1

exit /b 0


:SwitchEngine
set "TARGET_ENGINE=%~1"
set "CURRENT_ENGINE="
for /f "usebackq delims=" %%e in (`docker info --format "{{.OSType}}" 2^>nul`) do set "CURRENT_ENGINE=%%e"
if /i "!CURRENT_ENGINE!"=="!TARGET_ENGINE!" exit /b 0

echo Switching Docker Desktop to !TARGET_ENGINE! containers...
docker desktop engine use !TARGET_ENGINE!
if errorlevel 1 exit /b 1

for /l %%i in (1,1,90) do (
    set "CURRENT_ENGINE="
    for /f "usebackq delims=" %%e in (`docker info --format "{{.OSType}}" 2^>nul`) do set "CURRENT_ENGINE=%%e"
    if /i "!CURRENT_ENGINE!"=="!TARGET_ENGINE!" (
        echo Docker !TARGET_ENGINE! engine is ready.
        exit /b 0
    )
    timeout /t 2 /nobreak >nul
)

echo Error: Timed out waiting for the !TARGET_ENGINE! Docker engine.
exit /b 1
