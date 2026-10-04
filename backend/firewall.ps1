param([ValidateRange(1024,65535)][int]$Port=8765,[Parameter(Mandatory=$true)][string]$RuntimePath,[ValidateRange(0,2147483647)][int]$InterfaceIndex=0)
$ErrorActionPreference='Stop'
try {
    $runtime=(Resolve-Path -LiteralPath $RuntimePath).Path
    if ($InterfaceIndex -gt 0) {
        $profile=Get-NetConnectionProfile -InterfaceIndex $InterfaceIndex -ErrorAction Stop
        if ($profile.NetworkCategory -eq 'Public') {
            Set-NetConnectionProfile -InterfaceIndex $InterfaceIndex -NetworkCategory Private -ErrorAction Stop
        }
        $profile=Get-NetConnectionProfile -InterfaceIndex $InterfaceIndex -ErrorAction Stop
        if ($profile.NetworkCategory -ne 'Private') { throw 'Selected network is not private; domain policy is not changed.' }
    }
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
