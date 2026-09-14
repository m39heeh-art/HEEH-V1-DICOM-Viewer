# HEEH-V1 DICOM Viewer compatibility launcher.
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $scriptDir
& (Join-Path $scriptDir "launch.ps1")
