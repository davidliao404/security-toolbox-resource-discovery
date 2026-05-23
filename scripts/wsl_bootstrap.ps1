param(
    [string]$Distro = "Ubuntu-24.04",
    [string]$RepoPath = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"

function Convert-ToWslPath {
    param([string]$WindowsPath)
    $fullPath = (Resolve-Path $WindowsPath).Path
    if ($fullPath -notmatch "^([A-Za-z]):\\(.*)$") {
        throw "Only drive-letter paths are supported: $fullPath"
    }
    $drive = $matches[1].ToLowerInvariant()
    $rest = $matches[2] -replace "\\", "/"
    return "/mnt/$drive/$rest"
}

if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
    throw "wsl.exe is not available. Enable Windows Subsystem for Linux before running this script."
}

$installedRaw = & wsl.exe --list 2>$null
$installed = @($installedRaw | ForEach-Object { ($_ -replace "`0", "").Trim().TrimStart("*").Trim() } | Where-Object { $_ -and $_ -notmatch "Windows|Linux|NAME|FRIENDLY" })

$distroAvailable = $installed -contains $Distro
if (-not $distroAvailable) {
    $onlineRaw = & wsl.exe --list --online 2>$null
    $online = @($onlineRaw | ForEach-Object { ($_ -replace "`0", "").Trim() } | Where-Object { $_ })
    if (($Distro -eq "Ubuntu-24.04") -and ($online -match "^Ubuntu(\s|$)")) {
        Write-Host "Ubuntu-24.04 is not listed by this WSL build; falling back to Ubuntu from the online catalog."
        $Distro = "Ubuntu"
    }

    Write-Host "Installing WSL distribution $Distro"
    & wsl.exe --install --distribution $Distro --no-launch
    if ($LASTEXITCODE -ne 0) {
        throw "WSL distribution installation failed with exit code $LASTEXITCODE"
    }
    Write-Host "If Windows requests a restart or first-run Linux user creation, complete it and rerun this script."
}

$linuxRepoPath = Convert-ToWslPath $RepoPath
Write-Host "Using WSL distribution: $Distro"
Write-Host "Using repository path: $linuxRepoPath"

& wsl.exe -d $Distro --cd $linuxRepoPath -- bash scripts/wsl_bootstrap.sh
if ($LASTEXITCODE -ne 0) {
    throw "WSL bootstrap failed with exit code $LASTEXITCODE"
}
