$ErrorActionPreference = 'Stop'
$workspace = Split-Path $PSScriptRoot -Parent
$vbox = 'C:\Program Files\Oracle\VirtualBox\VBoxManage.exe'
if (-not (Test-Path -LiteralPath $vbox)) { throw 'Install Oracle VirtualBox first.' }
$iso = Join-Path $workspace 'downloads\debian-11.11.0-amd64-netinst.iso'
$sumFile = Join-Path $workspace 'downloads\SHA256SUMS'
$line = Get-Content -LiteralPath $sumFile | Where-Object { $_ -match '  debian-11\.11\.0-amd64-netinst\.iso$' }
if (-not $line -or (Get-FileHash -LiteralPath $iso -Algorithm SHA256).Hash -ne ($line -split '\s+')[0]) { throw 'ISO checksum mismatch.' }
function Invoke-VBox { & $vbox @args; if ($LASTEXITCODE -ne 0) { throw "VBoxManage failed: $($args[0])" } }
$name = 'AuraKingdom-V15'
$base = Join-Path $workspace 'vm'
$disk = Join-Path $base "$name\$name.vdi"
$existing = & $vbox list vms
if ($existing -match [regex]::Escape('"' + $name + '"')) { throw 'VM already exists; inspect it rather than overwriting.' }
Invoke-VBox createvm --name $name --ostype Debian_64 --basefolder $base --register
Invoke-VBox modifyvm $name --memory 4096 --cpus 4 --nic1 nat --clipboard-mode disabled --drag-and-drop disabled --boot1 dvd --boot2 disk
Invoke-VBox createmedium disk --filename $disk --size 81920 --format VDI --variant Standard
Invoke-VBox storagectl $name --name SATA --add sata --controller IntelAhci
Invoke-VBox storageattach $name --storagectl SATA --port 0 --device 0 --type hdd --medium $disk
Invoke-VBox storageattach $name --storagectl SATA --port 1 --device 0 --type dvddrive --medium $iso
Invoke-VBox showvminfo $name --machinereadable
Write-Output 'VM created, not booted. Install Debian with a private administrator password, SSH, and standard utilities; no desktop is needed.'
