# Genera el instalador de Vistana:
#   1. empaqueta la app con flet pack (PyInstaller) en dist\AnalizadorDelictual
#   2. compila instalador\vistana.iss con Inno Setup 6
# Resultado: instalador\salida\Vistana-<versión>-instalador.exe
# Uso (desde cualquier carpeta):  powershell -ExecutionPolicy Bypass -File instalador\construir.ps1
$ErrorActionPreference = "Stop"
$raiz = Split-Path $PSScriptRoot -Parent
Set-Location $raiz

# Una sola fuente para la versión: modulos\marca.py
$version = (Select-String -Path modulos\marca.py -Pattern '^VERSION = "(.+)"').Matches[0].Groups[1].Value
Write-Host "Vistana $version"

$iscc = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
    "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "No se encontró Inno Setup 6 (https://jrsoftware.org/isdl.php)." }

# Sin Iconos la ventana sale sin logo; sin recursos no se puede generar el informe PDF
& .venv\Scripts\flet.exe pack main.py -D -y --name AnalizadorDelictual `
    --icon Iconos\vistana_logo.ico --add-data "Iconos:Iconos" "recursos:recursos" `
    --product-name Vistana --file-description Vistana `
    --product-version $version --file-version "$version.0.0"
if ($LASTEXITCODE) { throw "flet pack falló" }

& $iscc "/DVersion=$version" instalador\vistana.iss
if ($LASTEXITCODE) { throw "Inno Setup falló" }
Write-Host "Instalador: $(Resolve-Path instalador\salida\Vistana-$version-instalador.exe)"
