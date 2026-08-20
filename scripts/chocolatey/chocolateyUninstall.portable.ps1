$ErrorActionPreference = 'Stop'

$packageName = $env:ChocolateyPackageName
$toolsDir    = Join-Path (Get-ToolsLocation) $packageName
$exePath     = Join-Path $toolsDir '{APP_NAME}.exe'

$desktopIcon = Join-Path ([Environment]::GetFolderPath('Desktop')) '{APP_NAME}.lnk'
$startIcon   = Join-Path ([Environment]::GetFolderPath('Programs')) '{APP_NAME}.lnk'

Remove-Item $desktopIcon -ErrorAction SilentlyContinue
Remove-Item $startIcon -ErrorAction SilentlyContinue

Uninstall-BinFile -Name '{APP_NAME}' -Path $exePath

if (Test-Path -LiteralPath $toolsDir) {
  # Keep portable user data across uninstall/reinstall
  Get-ChildItem -LiteralPath $toolsDir -Force -Exclude 'portable_data' |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}
