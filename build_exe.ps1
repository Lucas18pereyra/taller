param(
    [string]$Version = "1.2.0",
    [string]$CompanyName = "Lucas",
    [string]$ProductName = "Estacionamiento App",
    [switch]$Clean = $true
)

$ErrorActionPreference = "Stop"

function Get-VersionParts {
    param([string]$RawVersion)
    $parts = @()
    foreach ($p in ($RawVersion -split "\.")) {
        if ($p -match "^\d+$") {
            $parts += [int]$p
        }
    }
    while ($parts.Count -lt 4) {
        $parts += 0
    }
    if ($parts.Count -gt 4) {
        $parts = $parts[0..3]
    }
    return $parts
}

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    throw "No se encontro .venv\\Scripts\\python.exe en el proyecto."
}

$parts = Get-VersionParts -RawVersion $Version
$VersionText = "{0}.{1}.{2}.{3}" -f $parts[0], $parts[1], $parts[2], $parts[3]
$VersionTuple = "({0}, {1}, {2}, {3})" -f $parts[0], $parts[1], $parts[2], $parts[3]
$VersionFile = Join-Path $ProjectRoot "installer\version_info.txt"

$content = @"
# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=$VersionTuple,
    prodvers=$VersionTuple,
    mask=0x3F,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
        StringTable(
          u"040904B0",
          [
            StringStruct(u"CompanyName", u"$CompanyName"),
            StringStruct(u"FileDescription", u"Sistema de gestion de estacionamiento"),
            StringStruct(u"FileVersion", u"$VersionText"),
            StringStruct(u"InternalName", u"EstacionamientoApp"),
            StringStruct(u"LegalCopyright", u"(C) $CompanyName"),
            StringStruct(u"OriginalFilename", u"EstacionamientoApp.exe"),
            StringStruct(u"ProductName", u"$ProductName"),
            StringStruct(u"ProductVersion", u"$VersionText")
          ]
        )
      ]
    ),
    VarFileInfo([VarStruct(u"Translation", [1033, 1200])])
  ]
)
"@

Set-Content -Path $VersionFile -Value $content -Encoding UTF8

Push-Location $ProjectRoot
try {
    $args = @("-m", "PyInstaller")
    if ($Clean) {
        $args += "--clean"
    }
    $args += @("--noconfirm", "EstacionamientoApp.spec")

    & $PythonExe @args
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller finalizo con codigo $LASTEXITCODE."
    }

    $exePath = Join-Path $ProjectRoot "dist\EstacionamientoApp.exe"
    if (-not (Test-Path $exePath)) {
        throw "No se genero dist\\EstacionamientoApp.exe."
    }

    Write-Host "Build OK: $exePath"
    Write-Host "Version aplicada: $VersionText"
}
finally {
    Pop-Location
}
