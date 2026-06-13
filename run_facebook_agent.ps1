# run_facebook_agent.ps1 - keeps the Facebook agent alive on this PC.
#
# Forever loop:
#   1. Kills leftover Chrome/chromedriver holding the fb_chrome_profile
#      (the "zombie Chrome" that locks the profile and crashes new launches).
#   2. Removes stale Chrome profile LOCK files.
#   3. Starts `python facebook_agent.py` and waits.
#   4. If the agent exits/crashes, waits 30s and restarts it.
#
# Started at logon by the "DironetFacebookAgent" scheduled task.
# Manual test:  powershell -ExecutionPolicy Bypass -File run_facebook_agent.ps1
# NOTE: keep this file ASCII-only (PowerShell 5.1 misreads UTF-8 without BOM).

$ErrorActionPreference = "Continue"
$Root      = "C:\Users\itayl\OneDrive\Desktop\AGENTS"
$PyExe     = "C:\Users\itayl\AppData\Local\Python\pythoncore-3.14-64\python.exe"
$ProfileDir = Join-Path $Root "fb_chrome_profile"
$LogDir    = Join-Path $Root "logs"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

function Cleanup-Zombies {
    # Kill only Chrome/chromedriver tied to OUR profile - never the user's normal browsing.
    Get-CimInstance Win32_Process -Filter "Name='chrome.exe'" |
        Where-Object { $_.CommandLine -like "*fb_chrome_profile*" } |
        ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch {} }
    # Orphan chromedrivers (automation servers; the user never runs these by hand).
    Get-Process chromedriver -ErrorAction SilentlyContinue |
        ForEach-Object { try { Stop-Process -Id $_.Id -Force -ErrorAction Stop } catch {} }
    # Remove stale profile locks so a fresh Chrome can claim the profile.
    Get-ChildItem $ProfileDir -Recurse -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -eq "LOCK" -or $_.Name -like "Singleton*" } |
        ForEach-Object { try { Remove-Item $_.FullName -Force -ErrorAction Stop } catch {} }
}

$supLog = Join-Path $LogDir "facebook_supervisor.log"
$fbLog  = Join-Path $LogDir "facebook.log"
Set-Location $Root
while ($true) {
    Cleanup-Zombies
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $supLog -Value "[$stamp] starting facebook_agent.py"
    # -u = unbuffered, so logs/facebook.log updates live instead of buffering.
    & $PyExe -u (Join-Path $Root "facebook_agent.py") *>> $fbLog
    $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    Add-Content -Path $supLog -Value "[$stamp] agent exited (code $LASTEXITCODE) - restarting in 30s"
    Start-Sleep -Seconds 30
}
