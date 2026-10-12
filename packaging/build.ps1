param(
    [Parameter(Mandatory=$true)][string]$Python,
    [Parameter(Mandatory=$true)][string]$ISCC,
    [Parameter(Mandatory=$true)][string]$BuildRoot,
    [Parameter(Mandatory=$true)][string]$ReleaseDir
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$build = [System.IO.Path]::GetFullPath($BuildRoot)
$release = [System.IO.Path]::GetFullPath($ReleaseDir)
New-Item -ItemType Directory -Force -Path $build,$release | Out-Null
Push-Location $repo
try {
    & $Python -m PyInstaller --noconfirm --clean --workpath (Join-Path $build 'pyinstaller') --distpath (Join-Path $build 'dist') SonoCopilot.spec
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
    $bundle = Join-Path $build 'dist\SonoCopilot'
    & $ISCC ("/DBuildDir=" + $bundle) ("/DReleaseDir=" + $release) (Join-Path $PSScriptRoot 'SonoCopilot.iss')
    if ($LASTEXITCODE -ne 0) { throw 'Inno Setup build failed' }
    Get-ChildItem -LiteralPath $release -Filter '*.exe' | ForEach-Object {
        $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        Set-Content -LiteralPath ($_.FullName + '.sha256') -Value ($hash + '  ' + $_.Name) -Encoding ascii
    }
} finally { Pop-Location }
