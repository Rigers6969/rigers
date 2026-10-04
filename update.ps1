# Updates (or installs) the apps from GitHub - no zip downloading by hand.
# Run in PowerShell:
#   irm "https://raw.githubusercontent.com/Rigers6969/rigers/claude/sweet-dijkstra-lyzrb5/update.ps1?v=$(Get-Random)" | iex
# or double-click "Update Clip Factory" on the Desktop (update.bat).
#
# Clip Factory lives in ONE folder: C:\Users\<you>\ClipFactory (or inside the full rigers folder if you
# have that). The first run gathers your keys, settings, logins and clips from old downloaded copies
# into it. Nothing is ever deleted - files are only copied (videos are linked, so they use no extra space).

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$Branch = "claude/sweet-dijkstra-lyzrb5"
$Zip = "https://github.com/Rigers6969/rigers/archive/refs/heads/$Branch.zip"
$Home2 = $env:USERPROFILE
$ClipHome = Join-Path $Home2 "ClipFactory"
$DataFiles = @("ai_keys.json", "my_channels.json", "publisher.json", "publish_queue.json", "client_secret.json",
               "streamers.json", "podcasts.json", "trends_last.json", "rules_watch.json", "permissions.json",
               "channel_snapshots.json", "goals.json", "posts_seen.json", "prefs.json", "alerts.json", "campaigns.json")
$DataDirs = @("output", "input", "cache", "music", "gameplay", "watermarks")

function Say($text, $color = "Gray") { Write-Host $text -ForegroundColor $color }

function Find-Copies {
    # every Clip Factory folder (has clip_app.py) in your user folders, except AppData
    $found = @()
    Get-ChildItem -LiteralPath $Home2 -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notin @("AppData", "Application Data", "Local Settings") } |
        ForEach-Object {
            $found += Get-ChildItem -LiteralPath $_.FullName -Recurse -Depth 5 -Filter "clip_app.py" -File -ErrorAction SilentlyContinue
        }
    return $found | ForEach-Object { $_.Directory.FullName } | Select-Object -Unique
}

function Data-Time($dir) {
    # when this copy was last really used (its keys, settings, logins or clips changed)
    $t = [datetime]::MinValue
    foreach ($n in ($DataFiles + $DataDirs + @("tokens"))) {
        $p = Join-Path $dir $n
        if (Test-Path -LiteralPath $p) {
            $w = (Get-Item -LiteralPath $p).LastWriteTime
            if ($w -gt $t) { $t = $w }
        }
    }
    return $t
}

function Link-Tree($from, $to) {
    # puts every file of $from into $to (hard link = no extra space; copy if that fails), skips existing ones
    foreach ($f in @(Get-ChildItem -LiteralPath $from -Recurse -File -ErrorAction SilentlyContinue)) {
        $src = $f.FullName
        $rel = $src.Substring($from.Length).TrimStart('\', '/')
        $dst = Join-Path $to $rel
        if (Test-Path -LiteralPath $dst) { continue }
        New-Item -ItemType Directory -Path (Split-Path $dst -Parent) -Force | Out-Null
        $linked = $false
        try { New-Item -ItemType HardLink -Path $dst -Target $src -ErrorAction Stop | Out-Null; $linked = $true } catch { }
        if (-not $linked) {
            try { Copy-Item -LiteralPath $src -Destination $dst -Force -ErrorAction Stop }
            catch { Say "  (skipped $rel - couldn't copy it)" DarkGray }
        }
    }
}

function Bring-Data($old, $new) {
    foreach ($n in $DataFiles) {
        $p = Join-Path $old $n
        if (Test-Path -LiteralPath $p) { Copy-Item -LiteralPath $p -Destination (Join-Path $new $n) -Force }
    }
    $tok = Join-Path $old "tokens"
    if (Test-Path -LiteralPath $tok) {
        New-Item -ItemType Directory -Path (Join-Path $new "tokens") -Force | Out-Null
        Copy-Item -Path (Join-Path $tok "*") -Destination (Join-Path $new "tokens") -Force -ErrorAction SilentlyContinue
    }
    foreach ($d in $DataDirs) {
        $p = Join-Path $old $d
        if (Test-Path -LiteralPath $p) { Link-Tree $p (Join-Path $new $d) }
    }
    # the publish list remembers where each clip was - point it at the new folder
    $q = Join-Path $new "publish_queue.json"
    if (Test-Path -LiteralPath $q) {
        $text = [IO.File]::ReadAllText($q)
        $text = $text.Replace($old.Replace('\', '\\'), $new.Replace('\', '\\'))
        [IO.File]::WriteAllText($q, $text)
    }
}

function Make-Shortcut($name, $target, $workdir) {
    try {
        $desk = [Environment]::GetFolderPath("Desktop")
        $sh = New-Object -ComObject WScript.Shell
        $lnk = $sh.CreateShortcut((Join-Path $desk "$name.lnk"))
        $lnk.TargetPath = $target
        $lnk.WorkingDirectory = $workdir
        $lnk.Save()
        return $true
    } catch { return $false }
}

try {
    Say ""
    Say "Clip Factory updater v4" DarkGray
    Say "Looking for Clip Factory on this PC (can take a minute)..." Cyan
    $copies = @(Find-Copies)
    $full = $null
    foreach ($c in $copies) {
        $root = Split-Path $c -Parent
        if ((Split-Path $c -Leaf) -eq "clip-factory" -and (Test-Path -LiteralPath (Join-Path $root "web_server.py"))) { $full = $root; break }
    }
    if ($full) { $clip = Join-Path $full "clip-factory"; $dest = $full; Say "Found the full apps folder: $full" }
    else { $clip = $ClipHome; $dest = $ClipHome; Say "Clip Factory's home: $ClipHome" }

    $tmp = Join-Path $env:TEMP "_update_tmp"
    if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Recurse -Force }
    New-Item -ItemType Directory -Path $tmp | Out-Null
    # the exact newest version (by its commit), so GitHub's cache can never hand out an old copy
    $sha = $null
    try {
        $info = Invoke-RestMethod -Uri "https://api.github.com/repos/Rigers6969/rigers/commits/$Branch" -Headers @{ "User-Agent" = "clip-factory-updater" } -UseBasicParsing
        $sha = $info.sha
        $Zip = "https://github.com/Rigers6969/rigers/archive/$sha.zip"
    } catch { }
    # a Clip Factory that is still open would keep showing the old version - close it first
    try {
        $running = @(Get-CimInstance Win32_Process -ErrorAction Stop | Where-Object { $_.CommandLine -and $_.CommandLine -match "clip_app\.py" })
        if ($running.Count) {
            Say "Closing the Clip Factory that is still open..." Cyan
            $running | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
            Start-Sleep -Seconds 2
        }
    } catch { }
    Say "Downloading the newest version..." Cyan
    Invoke-WebRequest -Uri $Zip -OutFile (Join-Path $tmp "new.zip") -UseBasicParsing
    Expand-Archive -Path (Join-Path $tmp "new.zip") -DestinationPath $tmp -Force
    $src = (Get-ChildItem -LiteralPath $tmp -Directory | Select-Object -First 1).FullName
    if (-not $full) { $src = Join-Path $src "clip-factory" }

    Say "Installing..." Cyan
    New-Item -ItemType Directory -Path $dest -Force | Out-Null
    robocopy $src $dest /E /NFL /NDL /NJH /NJS /NP /R:2 /W:1 | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "Some files couldn't be replaced. Close Clip Factory (its black window) and run this again." }
    Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue

    # first time in this folder: bring keys, settings, logins and clips from the old copies (newest last, so it wins)
    $marker = Join-Path $clip ".moved-in"
    if (-not (Test-Path -LiteralPath $marker)) {
        $old = @($copies | Where-Object { $_ -ne $clip } | Sort-Object { Data-Time $_ })
        if ($old.Count) { Say "Bringing your keys, settings and clips from $($old.Count) old copies..." Cyan }
        foreach ($o in $old) {
            try { Bring-Data $o $clip }
            catch { Say "  (some files from $o couldn't be brought over: $($_.Exception.Message))" DarkGray }
        }
        Set-Content -LiteralPath $marker -Value (Get-Date -Format "yyyy-MM-dd HH:mm")
    }

    $version = if ($sha) { $sha.Substring(0, 7) } else { "latest" }
    Set-Content -LiteralPath (Join-Path $clip ".version") -Value ("$version " + (Get-Date -Format "yyyy-MM-dd HH:mm"))
    $ok1 = Make-Shortcut "Clip Factory" (Join-Path $clip "start.bat") $clip
    $ok2 = Make-Shortcut "Update Clip Factory" (Join-Path $clip "update.bat") $clip

    Say ""
    Say "Done - Clip Factory is up to date (version $version)." Green
    Say "Folder: $clip"
    if ($ok1 -and $ok2) { Say "On your Desktop: 'Clip Factory' starts it, 'Update Clip Factory' updates it." Green }
    if ($copies.Count -gt 1) {
        Say "Your old copies in Downloads aren't needed any more - you can delete them (your things are in $clip now)." Yellow
    }
    Say ""
    $answer = Read-Host "Start Clip Factory now? (y/n)"
    if ($answer -match "^[yY]") { Start-Process -FilePath (Join-Path $clip "start.bat") -WorkingDirectory $clip }
} catch {
    Say ""
    Say "Something went wrong:" Red
    Say $_.Exception.Message Red
    Say ("Where: " + $_.InvocationInfo.ScriptLineNumber + " | " + $_.InvocationInfo.Line.Trim()) DarkGray
    Say "Send a screenshot of this window to Claude." Yellow
}
