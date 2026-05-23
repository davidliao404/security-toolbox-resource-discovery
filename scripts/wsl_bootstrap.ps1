param(
    [string]$Distro = "Ubuntu-24.04",
    [string]$RepoPath = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
)

$ErrorActionPreference = "Stop"
if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

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

$distroAvailable = $false
& cmd.exe /c "wsl.exe -d $Distro -- true 2>nul"
if ($LASTEXITCODE -eq 0) {
    $distroAvailable = $true
}

if (-not $distroAvailable) {
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
