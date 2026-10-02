# Updates (or installs) the apps from GitHub - no zip downloading by hand.
# Run in PowerShell:
#   irm https://raw.githubusercontent.com/Rigers6969/rigers/claude/sweet-dijkstra-lyzrb5/update.ps1 | iex
# or double-click update.bat. Your own files (keys, config.json, videos, logins) are never touched:
# they aren't on GitHub, and nothing is deleted - new files are only copied over the old ones.

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$Zip = "https://github.com/Rigers6969/rigers/archive/refs/heads/claude/sweet-dijkstra-lyzrb5.zip"

function Find-Apps {
    # the full rigers folder (has web_server.py and clip-factory), else a lone clip-factory folder
    $places = @()
    Get-ChildItem -Path $env:USERPROFILE -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notin @("AppData", "Application Data", "Local Settings") } |
        ForEach-Object { $places += $_.FullName }
    $found = foreach ($p in $places) {
        Get-ChildItem -Path $p -Recurse -Depth 5 -Filter "clip_app.py" -ErrorAction SilentlyContinue
    }
    $found = $found | Where-Object { $_.FullName -notmatch "\\_update_tmp\\" } | Sort-Object LastWriteTime -Descending
    foreach ($f in $found) {
        $cf = $f.Directory.FullName
        $root = Split-Path $cf -Parent
        if (Test-Path (Join-Path $root "web_server.py")) { return @{ Kind = "full"; Path = $root } }
    }
    if ($found) { return @{ Kind = "clip"; Path = $found[0].Directory.FullName } }
    $default = Join-Path $env:USERPROFILE "rigers"
    if (Test-Path (Join-Path $default "web_server.py")) { return @{ Kind = "full"; Path = $default } }
    return @{ Kind = "new"; Path = $default }
}

Write-Host ""
Write-Host "Looking for your apps..." -ForegroundColor Cyan
$target = Find-Apps
if ($target.Kind -eq "new") { Write-Host "Not found - installing a fresh copy in $($target.Path)" }
else { Write-Host "Found: $($target.Path)" }

$tmp = Join-Path $env:TEMP "_update_tmp"
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
New-Item -ItemType Directory -Path $tmp | Out-Null
Write-Host "Downloading the newest version..." -ForegroundColor Cyan
try {
    Invoke-WebRequest -Uri $Zip -OutFile (Join-Path $tmp "new.zip") -UseBasicParsing
} catch {
    Write-Host "Download failed - check your internet and try again." -ForegroundColor Red
    Write-Host $_.Exception.Message
    return
}
Expand-Archive -Path (Join-Path $tmp "new.zip") -DestinationPath $tmp -Force
$src = Get-ChildItem -Path $tmp -Directory | Select-Object -First 1
$from = $src.FullName
if ($target.Kind -eq "clip") { $from = Join-Path $src.FullName "clip-factory" }

Write-Host "Updating..." -ForegroundColor Cyan
New-Item -ItemType Directory -Path $target.Path -Force | Out-Null
robocopy $from $target.Path /E /NFL /NDL /NJH /NJS /NP /R:2 /W:1 | Out-Null
if ($LASTEXITCODE -ge 8) {
    Write-Host "Some files couldn't be replaced. Close Clip Factory / Wayne Factory (their black windows) and run this again." -ForegroundColor Red
    return
}
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue

$clip = if ($target.Kind -eq "clip") { $target.Path } else { Join-Path $target.Path "clip-factory" }
Write-Host ""
Write-Host "Done - everything is up to date." -ForegroundColor Green
Write-Host "Folder: $($target.Path)"
Write-Host "Next time just double-click update.bat in that folder."
Write-Host ""
$answer = Read-Host "Start Clip Factory now? (y/n)"
if ($answer -match "^[yY]") {
    Start-Process -FilePath (Join-Path $clip "start.bat") -WorkingDirectory $clip
}
