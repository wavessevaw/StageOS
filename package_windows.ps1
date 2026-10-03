$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$release = 'src-tauri\target\x86_64-pc-windows-msvc\release'
if (!(Test-Path "$release\stageos.exe")) { throw 'Windows executable missing. Run build_windows.ps1 on Windows first.' }
New-Item -ItemType Directory -Force -Path 'artifacts\StageOS-Demo-Portable' | Out-Null
Copy-Item "$release\stageos.exe" 'artifacts\StageOS-Demo-Portable\StageOS.exe' -Force
Copy-Item 'dist\stageos-backend.exe' 'artifacts\StageOS-Demo-Portable\stageos-backend.exe' -Force
Copy-Item 'README_RU.md' 'artifacts\StageOS-Demo-Portable' -Force
Compress-Archive -Path 'artifacts\StageOS-Demo-Portable\*' -DestinationPath 'artifacts\StageOS-Demo-Portable.zip' -Force
$installer = Get-ChildItem "$release\bundle\nsis\*.exe" | Select-Object -First 1
if (!$installer) { throw 'NSIS installer missing' }
Copy-Item $installer.FullName 'artifacts\StageOS-Demo-Setup.exe' -Force
Write-Output 'Created StageOS-Demo-Setup.exe and StageOS-Demo-Portable.zip'
