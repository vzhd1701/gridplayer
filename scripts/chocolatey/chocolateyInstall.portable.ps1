$ErrorActionPreference = 'Stop'

$packageName   = $env:ChocolateyPackageName
$unzipLocation = Join-Path (Get-ToolsLocation) $packageName
$params        = Get-PackageParameters

$packageArgs = @{
  packageName    = $packageName
  unzipLocation  = $unzipLocation
  url64bit       = '{PACKAGE_URL}'
  checksum64     = '{PACKAGE_SHA256}'
  checksumType64 = 'sha256'
}

Install-ChocolateyZipPackage @packageArgs

# Zip root is GridPlayer/; hoist contents so the package dir is the app root
$nestedDir = Join-Path $unzipLocation '{APP_NAME}'
if (Test-Path -LiteralPath $nestedDir) {
  Get-ChildItem -LiteralPath $nestedDir -Force | Move-Item -Destination $unzipLocation -Force
  Remove-Item -LiteralPath $nestedDir -Recurse -Force
}

$exePath = Join-Path $unzipLocation '{APP_NAME}.exe'

Install-BinFile -Name '{APP_NAME}' -Path $exePath -UseStart

if ($params.DesktopIcon) {
  $desktopIcon = Join-Path ([Environment]::GetFolderPath('Desktop')) '{APP_NAME}.lnk'
  Write-Host -ForegroundColor White "Adding $desktopIcon"
  Install-ChocolateyShortcut -ShortcutFilePath $desktopIcon -TargetPath $exePath
}

if (-not $params.NoStart) {
  $startIcon = Join-Path ([Environment]::GetFolderPath('Programs')) '{APP_NAME}.lnk'
  Write-Host -ForegroundColor White "Adding $startIcon"
  Install-ChocolateyShortcut -ShortcutFilePath $startIcon -TargetPath $exePath
}
