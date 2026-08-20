$ErrorActionPreference = 'Stop'

$packageArgs = @{
  packageName    = $env:ChocolateyPackageName
  fileType       = 'exe'
  softwareName   = '{APP_NAME}*'
  url64bit       = '{PACKAGE_URL}'
  checksum64     = '{PACKAGE_SHA256}'
  checksumType64 = 'sha256'
  # Inno Setup
  silentArgs     = '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP-'
  validExitCodes = @(0)
}

Install-ChocolateyPackage @packageArgs
