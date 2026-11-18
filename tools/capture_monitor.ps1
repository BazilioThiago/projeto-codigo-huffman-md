$ErrorActionPreference = 'Stop'

$workspace = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$settingsPath = Join-Path $workspace '.vscode\settings.json'
$buildConfigPath = Join-Path $workspace 'build\config.env'
if (-not (Test-Path -LiteralPath $settingsPath)) {
    throw "Configuracoes do ESP-IDF nao encontradas: $settingsPath"
}
if (-not (Test-Path -LiteralPath $buildConfigPath)) {
    throw "Configuracao de build do ESP-IDF nao encontrada: $buildConfigPath"
}

$settings = Get-Content -Raw -LiteralPath $settingsPath | ConvertFrom-Json
$buildConfig = Get-Content -Raw -LiteralPath $buildConfigPath | ConvertFrom-Json
$idfPath = $settings.'idf.espIdfPathWin'
$toolsPath = $settings.'idf.toolsPathWin'
$pythonInstallPath = $settings.'idf.pythonInstallPath'
$idfVersionMatch = [regex]::Match([string]$buildConfig.IDF_VERSION, '^\d+\.\d+')
$pythonVersionMatch = [regex]::Match($pythonInstallPath, '\\(?<version>\d+\.\d+)\.\d+\\python\.exe$')
if (-not $idfPath -or -not $toolsPath -or -not $idfVersionMatch.Success -or -not $pythonVersionMatch.Success) {
    throw 'Nao foi possivel identificar os caminhos/versoes do ESP-IDF e Python nas configuracoes do workspace.'
}

$pythonEnvPath = Join-Path $toolsPath (
    'python_env\idf{0}_py{1}_env' -f $idfVersionMatch.Value, $pythonVersionMatch.Groups['version'].Value
)
$pythonEnvExecutable = Join-Path $pythonEnvPath 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath (Join-Path $idfPath 'export.ps1'))) {
    throw "Script de exportacao do ESP-IDF nao encontrado em: $idfPath"
}
if (-not (Test-Path -LiteralPath $pythonEnvExecutable)) {
    throw "Ambiente Python do ESP-IDF nao encontrado: $pythonEnvExecutable"
}

$env:IDF_TOOLS_PATH = $toolsPath
$env:IDF_PYTHON_ENV_PATH = $pythonEnvPath
. (Join-Path $idfPath 'export.ps1')
if (-not (Get-Command idf.py -ErrorAction SilentlyContinue)) {
    throw 'O ambiente do ESP-IDF foi carregado, mas idf.py nao foi encontrado no PATH.'
}

$target = Join-Path $workspace 'etapa2.log'
$stopFile = Join-Path $workspace ".etapa2-monitor-stop-$PID"
$existingLogs = @(
    Get-ChildItem -LiteralPath $workspace -Filter 'log.*.txt' -File |
        ForEach-Object { $_.FullName }
)

$targetStream = [System.IO.File]::Open(
    $target,
    [System.IO.FileMode]::OpenOrCreate,
    [System.IO.FileAccess]::ReadWrite,
    [System.IO.FileShare]::Read
)
try {
    if ($targetStream.Length -gt 0) {
        $targetStream.Position = $targetStream.Length - 1
        if ($targetStream.ReadByte() -ne 10) {
            $targetStream.Position = $targetStream.Length
            $targetStream.WriteByte(13)
            $targetStream.WriteByte(10)
        }
    }
}
finally {
    $targetStream.Dispose()
}

$copyJob = Start-Job -ArgumentList $workspace, $target, $existingLogs, $stopFile -ScriptBlock {
    param($workspace, $target, $existingLogs, $stopFile)

    $state = @{
        Source = $null
        Position = [long]0
    }

    $copyAvailableBytes = {
        if (-not $state.Source) {
            $candidate = Get-ChildItem -LiteralPath $workspace -Filter 'log.*.txt' -File |
                Where-Object { $_.FullName -notin $existingLogs } |
                Sort-Object LastWriteTime -Descending |
                Select-Object -First 1
            if ($candidate) {
                $state.Source = $candidate.FullName
            }
        }

        if ($state.Source -and (Test-Path -LiteralPath $state.Source)) {
            $inputStream = [System.IO.File]::Open(
                $state.Source,
                [System.IO.FileMode]::Open,
                [System.IO.FileAccess]::Read,
                [System.IO.FileShare]::ReadWrite
            )
            try {
                $inputStream.Position = $state.Position
                $buffer = New-Object byte[] 16384
                while (($count = $inputStream.Read($buffer, 0, $buffer.Length)) -gt 0) {
                    $outputStream = [System.IO.File]::Open(
                        $target,
                        [System.IO.FileMode]::Append,
                        [System.IO.FileAccess]::Write,
                        [System.IO.FileShare]::Read
                    )
                    try {
                        $outputStream.Write($buffer, 0, $count)
                        $outputStream.Flush()
                    }
                    finally {
                        $outputStream.Dispose()
                    }
                    $state.Position += $count
                }
            }
            finally {
                $inputStream.Dispose()
            }
        }
    }

    while (-not (Test-Path -LiteralPath $stopFile)) {
        & $copyAvailableBytes
        Start-Sleep -Milliseconds 100
    }

    & $copyAvailableBytes
    if (-not $state.Source) {
        throw 'O monitor nao criou o arquivo de log serial do ESP-IDF.'
    }
    $state.Source
}

try {
    Write-Host "Capturando a saida serial em $target"
    Push-Location $workspace
    idf.py monitor --save-log
    $monitorExit = $LASTEXITCODE
}
finally {
    New-Item -ItemType File -Path $stopFile -Force | Out-Null
    Wait-Job -Job $copyJob -Timeout 10 | Out-Null
    if ($copyJob.State -eq 'Running') {
        Stop-Job -Job $copyJob
    }
    $copyState = $copyJob.State
    $copyResult = @(Receive-Job -Job $copyJob -ErrorAction SilentlyContinue)
    Remove-Job -Job $copyJob -Force
    Remove-Item -LiteralPath $stopFile -Force -ErrorAction SilentlyContinue
    if ((Get-Location).Path -eq $workspace) {
        Pop-Location
    }
}

if ($copyState -ne 'Completed' -or -not $copyResult) {
    throw 'Falha ao copiar a saida do monitor. Verifique a tarefa e a porta serial.'
}
if ($monitorExit -ne 0) {
    exit $monitorExit
}
