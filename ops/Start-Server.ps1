$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
$vbox = 'C:\Program Files\Oracle\VirtualBox\VBoxManage.exe'
$info = & $vbox showvminfo 'AuraKingdom-V15' --machinereadable
if ($LASTEXITCODE -ne 0) { throw 'Could not find the AuraKingdom-V15 VM.' }
if ($info -notcontains 'VMState="running"') {
    & $vbox startvm 'AuraKingdom-V15' --type headless
    if ($LASTEXITCODE -ne 0) { throw 'VirtualBox could not start the VM.' }
}
Write-Host 'Waiting for the Linux VM...'
$ready = $false
for ($attempt = 0; $attempt -lt 60; $attempt++) {
    try {
        $probe = & python ops/vm.py run 'true' 2>$null
        if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    } catch {
        # SSH can reject connections while Debian is still booting.
    }
    Start-Sleep -Seconds 2
}
if (-not $ready) { throw 'VM SSH is not ready. Check the VM in VirtualBox.' }
& python ops/vm.py run 'systemctl start aurakingdom && systemctl is-active aurakingdom'
if ($LASTEXITCODE -ne 0) { throw 'Server startup failed. Check aurakingdom service logs.' }
Write-Host 'Services are starting. Allow about one minute for the channel to appear online.'
Write-Host 'Keep Tailscale connected, then open Play Aura Kingdom.lnk.'
