param([ValidateRange(1024,65535)][int]$Port=8765,[Parameter(Mandatory=$true)][string]$RuntimePath)
$ErrorActionPreference='Stop'
try {
    $runtime=(Resolve-Path -LiteralPath $RuntimePath).Path
    $name="StageOS-Server-$Port"
    Get-NetFirewallRule -Name $name -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    New-NetFirewallRule -Name $name -DisplayName "StageOS Server (private network, TCP $Port)" -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -Program $runtime -Profile Private -RemoteAddress LocalSubnet | Out-Null
    Write-Host 'StageOS Server: правило для частной локальной сети создано.'
} catch {Write-Error $_;exit 1}
