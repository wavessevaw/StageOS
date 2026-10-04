param([ValidateRange(1024,65535)][int]$Port=8765,[Parameter(Mandatory=$true)][string]$RuntimePath)
$ErrorActionPreference='Stop'
try {
    $runtime=(Resolve-Path -LiteralPath $RuntimePath).Path
    $name="StageOS-Server-$Port"
    Get-NetFirewallRule -Name $name -ErrorAction SilentlyContinue | Remove-NetFirewallRule
    New-NetFirewallRule -Name $name -DisplayName "StageOS Server (private network, TCP $Port)" -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -Program $runtime -Profile Private -RemoteAddress LocalSubnet | Out-Null
    $rule=Get-NetFirewallRule -Name $name -ErrorAction Stop
    if ($rule.Enabled -ne 'True' -or $rule.Action -ne 'Allow' -or $rule.Direction -ne 'Inbound') {
        throw 'Firewall rule verification failed.'
    }
    exit 0
} catch {
    try { $_ | Out-String | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'firewall-error.log') -Encoding UTF8 } catch {}
    exit 1
}
