$ErrorActionPreference = 'Stop'
$workspacePath = Split-Path -Parent $PSScriptRoot
$clientPath = Join-Path $workspacePath 'client\Requiem Aurakingdom'
$gamePath = Join-Path $clientPath 'Game.exe'
$gameBinaryPath = Join-Path $clientPath 'game.bin'

# Game.exe is a short-lived launcher; game.bin owns the actual game window.
# Window decorations alone cannot disable Direct3D's exclusive fullscreen.
$configPath = Join-Path $clientPath 'client.ini'
$configBytes = [IO.File]::ReadAllBytes($configPath)
$configText = [Text.Encoding]::GetEncoding(28591).GetString($configBytes)
$configText = [regex]::Replace($configText, '(?m)^FullScreenMode=\d+', 'FullScreenMode=0')
[IO.File]::WriteAllBytes($configPath, [Text.Encoding]::GetEncoding(28591).GetBytes($configText))

Add-Type @'
using System;
using System.Runtime.InteropServices;
public static class AuraBorderless {
    [StructLayout(LayoutKind.Sequential)] public struct Rect { public int Left, Top, Right, Bottom; }
    [StructLayout(LayoutKind.Sequential)] public struct MonitorInfo { public int Size; public Rect Monitor, Work; public uint Flags; }
    [DllImport("user32.dll")] static extern IntPtr MonitorFromWindow(IntPtr window, uint flags);
    [DllImport("user32.dll", CharSet=CharSet.Unicode)] static extern bool GetMonitorInfo(IntPtr monitor, ref MonitorInfo info);
    [DllImport("user32.dll", EntryPoint="GetWindowLongW", SetLastError=true)] static extern int GetStyle(IntPtr window, int index);
    [DllImport("user32.dll", EntryPoint="SetWindowLongW", SetLastError=true)] static extern int SetStyle(IntPtr window, int index, int style);
    [DllImport("user32.dll", SetLastError=true)] static extern bool SetWindowPos(IntPtr window, IntPtr after, int x, int y, int width, int height, uint flags);
    [DllImport("user32.dll")] static extern bool SetProcessDPIAware();
    public static void Prepare() { SetProcessDPIAware(); }
    public static void Apply(IntPtr window) {
        var info = new MonitorInfo(); info.Size = Marshal.SizeOf(typeof(MonitorInfo));
        if (!GetMonitorInfo(MonitorFromWindow(window, 2), ref info)) throw new InvalidOperationException("Cannot read game monitor bounds");
        int style = GetStyle(window, -16);
        style = (style & ~0x00CF0000) | unchecked((int)0x80000000);
        SetStyle(window, -16, style);
        var rect = info.Monitor;
        if (!SetWindowPos(window, IntPtr.Zero, rect.Left, rect.Top, rect.Right-rect.Left, rect.Bottom-rect.Top, 0x0060))
            throw new System.ComponentModel.Win32Exception(Marshal.GetLastWin32Error());
    }
}
'@
[AuraBorderless]::Prepare()
$gameProcess = Get-Process -Name 'game.bin' -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -eq $gameBinaryPath } | Select-Object -First 1
if (-not $gameProcess) {
    Start-Process -FilePath $gamePath -WorkingDirectory $clientPath -WindowStyle Normal
}
$deadline = [DateTime]::UtcNow.AddSeconds(60)
while ([DateTime]::UtcNow -lt $deadline) {
    $gameProcess = Get-Process -Name 'game.bin' -ErrorAction SilentlyContinue |
        Where-Object { $_.Path -eq $gameBinaryPath } | Select-Object -First 1
    if ($gameProcess -and $gameProcess.MainWindowHandle -ne [IntPtr]::Zero) {
        for ($attempt = 0; $attempt -lt 3; $attempt++) {
            [AuraBorderless]::Apply($gameProcess.MainWindowHandle)
            Start-Sleep -Milliseconds 500
        }
        exit 0
    }
    Start-Sleep -Milliseconds 250
}
throw 'Game window did not become ready within 60 seconds.'
