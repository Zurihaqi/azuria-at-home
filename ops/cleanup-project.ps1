$ErrorActionPreference = 'Stop'
$taskRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot)).TrimEnd('\')
$taskTargets = @(
    'client\Aura Kingdom V15 Clean',
    'staging\yokohiro',
    'staging\ultimate\hxsy\ZoneServer\ZoneServer.damage-cap-test',
    'downloads\client',
    'downloads\server',
    'downloads\bins',
    'downloads\database',
    'downloads\gatewayfix',
    'downloads\music',
    'downloads\official-client',
    'downloads\map-compat-source.tar.gz',
    'downloads\setup.tar',
    'downloads\MEGAcmdSetup64.exe',
    'downloads\megacmd-page.html',
    'downloads\vm-progress.png'
)
$taskProtected = @(
    'client\Requiem Aurakingdom\Game.exe',
    'client\Requiem Aurakingdom\game.bin',
    'client\Requiem Aurakingdom\connect.ini',
    'client\Requiem Aurakingdom\data\db\C_Item.ini',
    'client\Requiem Aurakingdom\data\db\C_Mission.ini',
    'bots\probe_login.py', 'dashboard\server.py', 'ops\Start-Server.ps1',
    'staging\ultimate\hxsy\ZoneServer\ZoneServer'
)
$taskHashes = @{}
foreach ($taskRel in $taskProtected) {
    $taskPath = Join-Path $taskRoot $taskRel
    if (Test-Path -LiteralPath $taskPath -PathType Leaf) {
        $taskHashes[$taskRel] = (Get-FileHash -LiteralPath $taskPath -Algorithm SHA256).Hash
    }
}
$taskReport = [ordered]@{
    timestamp_utc = [DateTime]::UtcNow.ToString('o')
    root = $taskRoot
    removed = @()
    total_removed_bytes = [long]0
    preserved = @('Active Requiem client', 'VM disks and snapshot chain', 'All private backups and credentials',
        'Dashboard and bot code', 'Primary server research files in staging/ultimate',
        'Original V15 recovered tables', 'Debian ISO referenced by VirtualBox')
    protected_sha256 = $taskHashes
    protected_files_verified = $false
}
$taskReportPath = Join-Path $taskRoot 'docs\project-cleanup.json'
foreach ($taskRel in $taskTargets) {
    $taskPath = [IO.Path]::GetFullPath((Join-Path $taskRoot $taskRel))
    if (-not $taskPath.StartsWith($taskRoot + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Cleanup target escapes workspace: $taskRel"
    }
    if (-not (Test-Path -LiteralPath $taskPath)) { continue }
    $taskItem = Get-Item -LiteralPath $taskPath -Force
    if ($taskItem.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "Refusing linked cleanup target: $taskRel"
    }
    $taskBytes = [long]0
    $taskCount = 0
    if ($taskItem.PSIsContainer) {
        Get-ChildItem -LiteralPath $taskPath -File -Force -Recurse | ForEach-Object {
            $taskBytes += $_.Length
            $taskCount++
        }
    } else {
        $taskBytes = $taskItem.Length
        $taskCount = 1
    }
    Write-Output ('Removing {0}: {1:N2} GiB ({2} files)' -f $taskRel, ($taskBytes / 1GB), $taskCount)
    Remove-Item -LiteralPath $taskPath -Force -Recurse
    if (Test-Path -LiteralPath $taskPath) { throw "Target still exists: $taskRel" }
    $taskReport.removed += [ordered]@{path=$taskRel; bytes=$taskBytes; files=$taskCount}
    $taskReport.total_removed_bytes += $taskBytes
    $taskReport | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $taskReportPath -Encoding utf8
}
foreach ($taskRel in $taskHashes.Keys) {
    $taskActual = (Get-FileHash -LiteralPath (Join-Path $taskRoot $taskRel) -Algorithm SHA256).Hash
    if ($taskActual -ne $taskHashes[$taskRel]) { throw "Protected file changed: $taskRel" }
}
$taskReport.protected_files_verified = $true
$taskReport | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $taskReportPath -Encoding utf8
Write-Output ('Removed {0:N2} GiB. Protected file hashes unchanged.' -f ($taskReport.total_removed_bytes / 1GB))
