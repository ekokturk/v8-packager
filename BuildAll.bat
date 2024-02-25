@echo off

for /f "tokens=2 delims= " %%v in ('python3 --version 2^>^&1') do set PYTHON_VERSION=%%v
for /f "tokens=1,2 delims=." %%a in ("%PYTHON_VERSION%") do (
    set MAJOR=%%a
    set MINOR=%%b
)
if %MAJOR% equ 3 (
    if %MINOR% lss 6 (
        echo Invalid Python version.
    )
) else  (
    echo Invalid Python version.
)

python3 -m venv .venv
call .venv\Scripts\activate

pip install -r requirements.txt

IF "%1"=="" (
    python3 run.py --fetch
) ELSE (
    python3 run.py --fetch --version %1
)

python3 run.py --build

wsl --list -q >nul 2>&1
if %errorlevel% equ 0 (
    wsl python3 -m venv .venv/linux; source .venv/linux/bin/activate; pip install -r requirements.txt; python3 run.py --build; deactivate
) else (
    echo WSL is not installed on this system. Unable to build Linux and Android.
)

python3 run.py --archive

deactivate