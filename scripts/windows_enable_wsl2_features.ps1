param(
    [switch]$NoRestart
)

$ErrorActionPreference = "Stop"

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdministrator)) {
    $argsList = @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$PSCommandPath`""
    )
    if ($NoRestart) {
        $argsList += "-NoRestart"
    }
    Start-Process -FilePath "powershell.exe" -ArgumentList $argsList -Verb RunAs -Wait
    exit $LASTEXITCODE
}

dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart

try {
    bcdedit /set hypervisorlaunchtype auto
} catch {
    Write-Warning "Unable to set hypervisorlaunchtype automatically: $($_.Exception.Message)"
}

wsl.exe --set-default-version 2

Write-Host "WSL2 Windows features are enabled. Restart Windows before installing the Ubuntu distribution."
if (-not $NoRestart) {
    Write-Host "Restarting Windows in 15 seconds. Close any unsaved work now."
    shutdown.exe /r /t 15 /c "Restarting to finish WSL2 feature enablement for resource discovery gateway validation."
}
