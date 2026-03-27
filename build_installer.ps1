param(
    [string]$InnoCompiler = ""
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$IssPath = Join-Path $ProjectRoot "installer\EstacionamientoApp.iss"
if (-not (Test-Path $IssPath)) {
    throw "No se encontro installer\\EstacionamientoApp.iss."
}

if ([string]::IsNullOrWhiteSpace($InnoCompiler)) {
    $candidatos = @(
        "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )
    foreach ($c in $candidatos) {
        if (Test-Path $c) {
            $InnoCompiler = $c
            break
        }
    }
}

if ([string]::IsNullOrWhiteSpace($InnoCompiler) -or -not (Test-Path $InnoCompiler)) {
    throw "No se encontro ISCC.exe. Instala Inno Setup 6 o pasa -InnoCompiler."
}

Push-Location (Join-Path $ProjectRoot "installer")
try {
    & $InnoCompiler "EstacionamientoApp.iss"
    if ($LASTEXITCODE -ne 0) {
        throw "ISCC finalizo con codigo $LASTEXITCODE."
    }
    Write-Host "Instalador generado en dist_installer\\"
}
finally {
    Pop-Location
}
