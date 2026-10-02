# Updates (or installs) the apps from GitHub - no zip downloading by hand.
# Run in PowerShell:
#   irm https://raw.githubusercontent.com/Rigers6969/rigers/claude/sweet-dijkstra-lyzrb5/update.ps1 | iex
# or double-click "Update Clip Factory" on the Desktop (update.bat).
#
# Clip Factory lives in ONE folder: C:\Users\<you>\ClipFactory (or inside the full rigers folder if you
# have that). The first run gathers your keys, settings, logins and clips from old downloaded copies
# into it. Nothing is ever deleted - files are only copied (videos are linked, so they use no extra space).

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$Zip = "https://github.com/Rigers6969/rigers/archive/refs/heads/claude/sweet-dijkstra-lyzrb5.zip"
$Home2 = $env:USERPROFILE
$ClipHome = Join-Path $Home2 "ClipFactory"
$DataFiles = @("ai_keys.json", "my_channels.json", "publisher.json", "publish_queue.json", "client_secret.json",
               "streamers.json", "podcasts.json", "trends_last.json", "rules_watch.json", "permissions.json",
               "channel_snapshots.json")
$DataDirs = @("output", "input", "cache")

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
    Get-ChildItem -LiteralPath $from -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
        $rel = $_.FullName.Substring($from.Length).TrimStart('\', '/')
        $dst = Join-Path $to $rel
        if (-not (Test-Path -LiteralPath $dst)) {
            New-Item -ItemType Directory -Path (Split-Path $dst -Parent) -Force | Out-Null
            try { New-Item -ItemType HardLink -Path $dst -Target $_.FullName -ErrorAction Stop | Out-Null }
            catch { Copy-Item -LiteralPath $_.FullName -Destination $dst -Force }
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
        foreach ($o in $old) { Bring-Data $o $clip }
        Set-Content -LiteralPath $marker -Value (Get-Date -Format "yyyy-MM-dd HH:mm")
    }

    $ok1 = Make-Shortcut "Clip Factory" (Join-Path $clip "start.bat") $clip
    $ok2 = Make-Shortcut "Update Clip Factory" (Join-Path $clip "update.bat") $clip

    Say ""
    Say "Done - Clip Factory is up to date." Green
    Say "Folder: $clip"
    if ($ok1 -and $ok2) { Say "On your Desktop: 'Clip Factory' starts it, 'Update Clip Factory' updates it." Green }
    if ($copies.Count -gt 1 -and -not $full) {
        Say "Your old copies in Downloads aren't needed any more - you can delete them (your things are in $clip now)." Yellow
    }
    Say ""
    $answer = Read-Host "Start Clip Factory now? (y/n)"
    if ($answer -match "^[yY]") { Start-Process -FilePath (Join-Path $clip "start.bat") -WorkingDirectory $clip }
} catch {
    Say ""
    Say "Something went wrong:" Red
    Say $_.Exception.Message Red
    Say "Send a screenshot of this window to Claude." Yellow
}
