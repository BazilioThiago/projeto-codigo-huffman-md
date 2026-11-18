param([string]$CompilerBin = 'C:\Program Files\CodeBlocks\MinGW\bin')
$ErrorActionPreference='Stop'
$root=Split-Path $PSScriptRoot -Parent
$env:Path="$CompilerBin;$env:Path"
Push-Location $root
try {
    New-Item -ItemType Directory -Force resultados/cobertura | Out-Null
    # Clear only generated counters for this executable, never aggregate old campaigns.
    Remove-Item resultados/cobertura/test_huffman.gcda -ErrorAction SilentlyContinue
    gcc -std=c11 -Wall -Wextra -Werror -O0 --coverage tests/test_huffman.c -o resultados/cobertura/test_huffman.exe
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao compilar testes' }
    ./resultados/cobertura/test_huffman.exe
    if ($LASTEXITCODE -ne 0) { throw 'Teste Huffman falhou' }
    gcov -b -c -o resultados/cobertura/test_huffman.gcno tests/test_huffman.c | Tee-Object resultados/cobertura/resumo.txt
    if ($LASTEXITCODE -ne 0) { throw 'gcov falhou' }
    Move-Item -Force huffman.c.gcov,test_huffman.c.gcov resultados/cobertura/
} finally { Pop-Location }
