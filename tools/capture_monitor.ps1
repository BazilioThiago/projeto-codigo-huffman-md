param(
    [string]$Port = 'COM3',
    [string]$OutputDir = 'resultados',
    [switch]$BuildFlash,
    [string]$PythonExecutable,
    [string]$IdfPath
)
$ErrorActionPreference = 'Stop'
$workspace = Split-Path $PSScriptRoot -Parent
$settingsPath = Join-Path $workspace '.vscode/settings.json'
$settings = if (Test-Path $settingsPath) { Get-Content $settingsPath -Raw | ConvertFrom-Json } else { $null }
if (-not $IdfPath) { $IdfPath = $env:IDF_PATH }
if (-not $IdfPath -and $settings) { $IdfPath = $settings.'idf.espIdfPathWin' }
if (-not $env:IDF_TOOLS_PATH -and $settings) { $env:IDF_TOOLS_PATH = $settings.'idf.toolsPathWin' }
$env:PYTHONUTF8 = '1'
if (-not $PythonExecutable -and $env:IDF_PYTHON_ENV_PATH) {
    $PythonExecutable = Join-Path $env:IDF_PYTHON_ENV_PATH 'Scripts/python.exe'
}
if (-not $PythonExecutable -and $env:IDF_TOOLS_PATH) {
    $envDirs = @(Get-ChildItem (Join-Path $env:IDF_TOOLS_PATH 'python_env') -Directory | Where-Object { Test-Path (Join-Path $_.FullName 'Scripts/python.exe') })
    if ($envDirs.Count -ne 1) { throw 'Nao foi identificado um unico ambiente IDF: informe -PythonExecutable ou ative o ESP-IDF no terminal.' }
    $env:IDF_PYTHON_ENV_PATH = $envDirs[0].FullName
    $PythonExecutable = Join-Path $env:IDF_PYTHON_ENV_PATH 'Scripts/python.exe'
}
if (-not $PythonExecutable) { $PythonExecutable = (Get-Command python -ErrorAction Stop).Source }
if (-not (Test-Path -LiteralPath $PythonExecutable)) { throw "Python nao encontrado: $PythonExecutable" }
$env:Path = "$(Split-Path $PythonExecutable);$env:Path"
Push-Location $workspace
try {
    if ($BuildFlash) {
        if (-not $IdfPath -or -not (Test-Path (Join-Path $IdfPath 'export.ps1'))) {
            throw 'Ative o ESP-IDF no terminal ou informe -IdfPath para compilar/gravar.'
        }
        . (Join-Path $IdfPath 'export.ps1')
        idf.py -p $Port build flash
        if ($LASTEXITCODE -ne 0) { throw 'Build/flash falhou.' }
    }
    & $PythonExecutable tools/capture_serial.py --port $Port --output $OutputDir
    if ($LASTEXITCODE -ne 0) { throw 'Captura incompleta; consulte a mensagem acima e a pasta da execucao.' }
} finally { Pop-Location }
