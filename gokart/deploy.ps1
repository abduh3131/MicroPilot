param (
    [Parameter(Mandatory = $true)]
    [string]$TargetIP,
    [string]$KeyFile = "system/hardware/tici/id_rsa"
)


$filesToDeploy = @(
    @{ Src = "tools/webcam/camerad.py"; Dst = "/data/openpilot/tools/webcam/camerad.py" },
    @{ Src = "tools/webcam/esp32_usb_bridge.py"; Dst = "/data/openpilot/tools/webcam/esp32_usb_bridge.py" }
)

$identityFile = $KeyFile
$port = 22
$user = "comma"

Write-Host "Deploying files to $user@$TargetIP..."

# Check if identity file exists
if (-not (Test-Path $identityFile)) {
    Write-Error "Identity file not found at $identityFile. Please check your openpilot directory structure."
    exit 1
}

# Run SCP command for each file
foreach ($file in $filesToDeploy) {
    Write-Host "Copying $($file.Src) to $($file.Dst)..."
    scp -i $identityFile -P $port $file.Src "${user}@${TargetIP}:$($file.Dst)"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Failed to copy $($file.Src)" -ForegroundColor Red
    }
}

Write-Host "Deployment process finished." -ForegroundColor Green
