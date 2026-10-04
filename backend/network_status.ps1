param([ValidateRange(1024,65535)][int]$Port=8765,[Parameter(Mandatory=$true)][string]$RuntimePath)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false)
try {
    $profiles=@(Get-NetConnectionProfile | ForEach-Object {
        @{name=[string]$_.Name;interface=[string]$_.InterfaceAlias;category=[string]$_.NetworkCategory;index=[int]$_.InterfaceIndex}
    })
    $rule=Get-NetFirewallRule -PolicyStore ActiveStore -Name "StageOS-Server-$Port" -ErrorAction SilentlyContinue
    $state='missing'
    if ($rule) {
        $state='mismatch'
        $app=$rule | Get-NetFirewallApplicationFilter
        $ports=$rule | Get-NetFirewallPortFilter
        $addresses=$rule | Get-NetFirewallAddressFilter
        if ($rule.Enabled -eq 'True' -and $rule.Action -eq 'Allow' -and $rule.Direction -eq 'Inbound' -and [string]$rule.Profile -eq 'Private' -and $app.Program -eq $RuntimePath -and [string]$ports.LocalPort -eq [string]$Port -and [string]$ports.Protocol -in @('TCP','6') -and 'LocalSubnet' -in $addresses.RemoteAddress) {
            $state='allowed'
        }
    }
    @{profiles=$profiles;firewall=$state} | ConvertTo-Json -Depth 4 -Compress
    exit 0
} catch {exit 1}
