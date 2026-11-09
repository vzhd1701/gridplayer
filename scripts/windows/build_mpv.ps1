<#
Build the mpv fork for 64-bit Windows: the app folder, a portable zip and,
where Inno Setup is there, an installer.

Run from anywhere:
    powershell -ExecutionPolicy Bypass -File scripts\windows\build_mpv.ps1

Needs uv and Python 3.10. Inno Setup is looked for in .local-tools\inno and
where it installs itself; pass -SkipInstaller to go without.
#>
param(
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"

$MpvUrl = "https://github.com/shinchiro/mpv-winbuild-cmake/releases/download/20261109/mpv-dev-x86_64-20261109-git-8bc468896e.7z"
$MpvSha256 = "4e888424015f7146893d03c4d40e2aaf9474d8d47e761bcc6a97489008a7e425"
$PyInstallerVersion = "6.22.3"
$PythonVersion = "3.10"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$Build = Join-Path $Root "build"
$Dist = Join-Path $Root "dist"
$LocalTools = Join-Path $Root ".local-tools"
$Scripts = Join-Path $Root "scripts"
$Utf8 = New-Object System.Text.UTF8Encoding($false)

Set-Location $Root

function Invoke-Native {
    param([string]$Exe, [string[]]$Arguments)

    & $Exe @Arguments

    if ($LASTEXITCODE -ne 0) {
        throw "$Exe failed with exit code $LASTEXITCODE"
    }
}

function Find-Tool {
    param([string]$Command, [string[]]$Candidates)

    foreach ($candidate in $Candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    $found = Get-Command $Command -ErrorAction SilentlyContinue

    if ($found) {
        return $found.Source
    }

    return $null
}

function Read-AppVars {
    $text = [IO.File]::ReadAllText((Join-Path $Root "gridplayer\version.py"))

    $get = {
        param($name)
        $match = [regex]::Match($text, "__${name}__ = `"([^`"]*)`"")
        if (-not $match.Success) { throw "$name is not in version.py" }
        $match.Groups[1].Value
    }

    $version = & $get "version"

    return @{
        APP_MODULE          = "gridplayer"
        APP_NAME            = & $get "app_name"
        APP_DISP_NAME       = & $get "display_name"
        APP_ID              = & $get "app_id"
        APP_AUTHOR          = & $get "author_name"
        APP_URL             = & $get "app_url"
        APP_VERSION         = $version
        APP_VERSION_NUMERIC = [regex]::Match($version, "^\d+\.\d+\.\d+").Value
    }
}

function Copy-WithAppVars {
    param([string]$Source, [string]$Destination, [hashtable]$Vars)

    $text = [IO.File]::ReadAllText($Source, $Utf8)

    foreach ($key in $Vars.Keys) {
        $text = $text.Replace("{$key}", $Vars[$key])
    }

    [IO.File]::WriteAllText($Destination, $text, $Utf8)
}

function Get-LibMpvArchive {
    $local = Join-Path $LocalTools "dl-mpv\mpv-dev.7z"
    $cached = Join-Path $Build "mpv-dev.7z"

    foreach ($candidate in @($local, $cached)) {
        if ((Test-Path $candidate) -and
            (Get-FileHash $candidate -Algorithm SHA256).Hash -ieq $MpvSha256) {
            return $candidate
        }
    }

    Write-Host "Downloading libmpv"

    $ProgressPreference = "SilentlyContinue"
    $part = "$cached.part"
    Invoke-WebRequest -UseBasicParsing -Uri $MpvUrl -OutFile $part

    if ((Get-FileHash $part -Algorithm SHA256).Hash -ine $MpvSha256) {
        Remove-Item $part -Force
        throw "The libmpv download does not match its checksum"
    }

    Move-Item $part $cached -Force

    return $cached
}

$vars = Read-AppVars
$appName = $vars.APP_NAME
$appDist = Join-Path $Dist $appName
$artifactBase = "$appName-mpv-$($vars.APP_VERSION)-win64"

$uv = Find-Tool "uv" @(Join-Path $LocalTools "uv\uv.exe")

if (-not $uv) {
    throw "uv was not found"
}

New-Item -ItemType Directory -Force $Build, $Dist | Out-Null

Write-Host "Preparing the build environment"

$env:UV_PYTHON_PREFERENCE = "only-system"

$venv = Join-Path $Build "venv-pyinstaller"
$python = Join-Path $venv "Scripts\python.exe"
$requirements = Join-Path $Build "requirements.txt"

Invoke-Native $uv @(
    "export", "--quiet", "--locked", "--no-dev", "--no-hashes",
    "--no-emit-project", "--format", "requirements-txt", "-o", $requirements
)

if (-not (Test-Path $python)) {
    Invoke-Native $uv @("venv", "--quiet", "--python", $PythonVersion, $venv)
}

Invoke-Native $uv @("pip", "install", "--quiet", "--python", $python, "-r", $requirements)
Invoke-Native $uv @("pip", "install", "--quiet", "--python", $python, "pyinstaller==$PyInstallerVersion")

Write-Host "Building the app folder"

Copy-Item (Join-Path $Root "resources\icons\main\sys\windows.ico") (Join-Path $Build "main.ico") -Force
Copy-Item (Join-Path $Root "resources\icons\playlist\sys\windows.ico") (Join-Path $Build "mime.ico") -Force

Copy-WithAppVars (Join-Path $Scripts "pyinstaller\version_info.py") (Join-Path $Build "version_info.py") $vars

$spec = Join-Path $Build "$appName.spec"
Copy-WithAppVars (Join-Path $Scripts "pyinstaller\pyinstaller_win.spec") $spec $vars

if (Test-Path $appDist) {
    Remove-Item $appDist -Recurse -Force
}

Invoke-Native $python @("-m", "PyInstaller", "--clean", "--noconfirm", "--distpath", $Dist, "--workpath", (Join-Path $Build "pyinstaller"), $spec)

Write-Host "Embedding libmpv"

$archive = Get-LibMpvArchive
$extracted = Join-Path $Build "libmpv-extract"

if (Test-Path $extracted) {
    Remove-Item $extracted -Recurse -Force
}

New-Item -ItemType Directory -Force $extracted | Out-Null
Invoke-Native "tar.exe" @("-xf", $archive, "-C", $extracted)

$embedded = Join-Path $appDist "libmpv"
New-Item -ItemType Directory -Force $embedded | Out-Null
Copy-Item (Join-Path $extracted "libmpv-2.dll") $embedded

Write-Host "Building the portable zip"

$portableData = Join-Path $appDist "portable_data"
$zip = Join-Path $Dist "$artifactBase-portable.zip"

if (Test-Path $zip) {
    Remove-Item $zip -Force
}

New-Item -ItemType Directory -Force $portableData | Out-Null
Invoke-Native "tar.exe" @("-a", "-cf", $zip, "-C", $Dist, $appName)
Remove-Item $portableData -Force

if ($SkipInstaller) {
    Write-Host "Skipping the installer, as asked"
    return
}

$iscc = Find-Tool "iscc" @(
    (Join-Path $LocalTools "inno\ISCC.exe"),
    "${env:ProgramFiles(x86)}\Inno Setup 7\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 7\ISCC.exe",
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
)

if (-not $iscc) {
    throw "Inno Setup was not found; pass -SkipInstaller to go without"
}

Write-Host "Building the installer"

$iss = Join-Path $Build "installer.iss"
Copy-WithAppVars (Join-Path $Scripts "windows\installer.iss") $iss ($vars + @{ APP_SRC = $appDist })

$env:PYTHONPATH = $Root
Invoke-Native $python @(
    (Join-Path $Scripts "windows\generate_file_associations.py"),
    "{APP_FILE_ASSOCIATIONS}", $iss
)
Remove-Item Env:\PYTHONPATH

Invoke-Native $iscc @("/Qp", "/O$Dist", "/F$artifactBase-install", $iss)

Write-Host "Done: $Dist"
