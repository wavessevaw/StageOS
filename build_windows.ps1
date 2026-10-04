param([ValidateSet('Portable','Tauri')][string]$Mode = 'Portable')
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if ($env:OS -ne 'Windows_NT') { throw 'Build script requires Windows 10/11 x64, Python 3.12 and Node 20+. Tauri mode additionally requires Rust MSVC and C++ Build Tools.' }
function Run-Native([string]$Program, [string[]]$Arguments) {
    & $Program @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Program failed with exit code $LASTEXITCODE" }
}
Run-Native 'py' @('-3.12','-m','venv','.venv')
$py = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
Run-Native $py @('-m','pip','install','-r','requirements-lock.txt')
Run-Native 'npm.cmd' @('ci','--prefix','frontend')
Run-Native 'npm.cmd' @('run','build','--prefix','frontend')
Run-Native $py @('-m','pytest','tests','-q')
if ($Mode -eq 'Portable') {
    Run-Native $py @('-m','pip','install','ziglang==0.16.0')
    Run-Native $py @('scripts/fetch_windows_runtime.py')
    Run-Native $py @('-m','ziglang','cc','-target','x86_64-windows-gnu','-municode','-Wl,--subsystem,windows','-O2','-s','windows/launcher.c','-o','windows/StageOS.exe')
    Run-Native $py @('scripts/assemble_windows_portable.py')
    Compress-Archive -Path 'artifacts/StageOS-Portable' -DestinationPath 'artifacts/StageOS-Portable.zip' -Force
    Write-Output 'Created artifacts/StageOS-Portable.zip'
    exit 0
}

Run-Native $py @('-m','PyInstaller','--noconfirm','--clean','--onefile','--name','stageos-backend','--collect-all','ortools','--collect-all','uvicorn','--collect-all','alembic','--hidden-import','sqlalchemy.dialects.sqlite','--add-data','frontend/dist;frontend/dist','--add-data','migrations;migrations','--paths','.','backend/launcher.py')
New-Item -ItemType Directory -Force -Path 'src-tauri\binaries' | Out-Null
Copy-Item 'dist\stageos-backend.exe' 'src-tauri\binaries\stageos-backend-x86_64-pc-windows-msvc.exe' -Force
Run-Native 'npm.cmd' @('ci')
Run-Native 'npm.cmd' @('run','tauri','--','build','--target','x86_64-pc-windows-msvc')
& (Join-Path $PSScriptRoot 'package_windows.ps1')
