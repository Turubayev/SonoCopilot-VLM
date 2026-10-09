$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$sonoPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (-not (Test-Path -LiteralPath $sonoPython)) {
    $sonoPython = (Get-Command python -ErrorAction Stop).Source
}
& $sonoPython -c 'import PIL, numpy, pydicom'
if ($LASTEXITCODE -ne 0) {
    & $sonoPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Не удалось установить зависимости.' }
}
Write-Host 'Откройте http://127.0.0.1:8765 в браузере. Ctrl+C — остановить.'
& $sonoPython server.py
