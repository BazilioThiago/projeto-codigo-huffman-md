# Medicoes de tempo de resposta: Huffman / ESP32

Thiago Bazilio e Guilherme Santana - Engenharia de Computacao.

## Executar na placa

Feche o monitor do VS Code antes de executar. A COM3 so pode ter um leitor.
No PowerShell, na pasta do projeto:

```powershell
./tools/capture_monitor.ps1 -BuildFlash
```

Compila, grava na COM3, reinicia a ESP32 e captura tudo automaticamente.
Para repetir com o firmware ja gravado:

```powershell
./tools/capture_monitor.ps1
```

Nao abra outro monitor. Nao precisa apertar reset nem interromper com Ctrl+C.
O programa termina sozinho apos quatro etapas (~7 minutos mais compilacao).
Cada execucao cria `resultados/AAAAMMDD_HHMMSS/`, sem sobrescrever as anteriores.
Uma execucao valida tem `complete.json`, quatro CSVs e `serial.log`.
Uma captura interrompida ou com erro nao recebe marcador de conclusao.
A etapa 4 demora cerca de 300 segundos sem imprimir: os tempos ficam na RAM.

## O que esta sendo medido

ESP32 de dois nucleos, 160 MHz fixos, FreeRTOS com tick de 1 ms, ESP-IDF 6.1,
compilacao Debug (-Og), sem gerenciamento dinamico de energia. Mesma tarefa
C em todas as etapas: frequencias, arvore, codificacao, decodificacao,
comparacao e liberacao da memoria. Array de 1024 bytes; srand(42) reiniciado
em cada etapa. Geracao da entrada fora do trecho medido.

1. 1000 execucoes isoladas; clock_gettime(CLOCK_MONOTONIC) antes/depois.
2. 1000 eventos de timer de disparo unico; proximo evento so e armado apos
   terminar a ativacao anterior. Resposta contada desde o instante nominal
   do alarme, incluindo entrega da interrupcao e escalonamento.
3. 1000 ativacoes periodicas (30 ms) e duas tarefas concorrentes no core 1:
   alta prioridade 5 (4 ms/500 us de trabalho) e baixa prioridade 2
   (25 ms/1200 us), com mutex e heranca de prioridade. Huffman prioridade 3.
4. 10000 ativacoes como etapa 3, mais IRQ de 120 us a cada 500 us no core 1
   e acessos sinteticos a 32 KiB de RAM no core 0. Nao se afirma que essa
   carga reproduza rede real nem que sature cache: e estresse sintetico.

Nos cenarios com timer, o inicio nominal e calculado com CLOCK_MONOTONIC
antes de iniciar o GPTimer de 1 MHz. O custo entre essa leitura e o start
introduz pequeno vies conservador; nao ha calibracao externa da fase/deriva.
A fila preserva ate 32 liberacoes; overflow invalida a campanha.
Os tempos incluem bloqueio por mutex e preempcao. A impressao dos CSVs
ocorre so depois de parar os timers e concorrentes de cada etapa.
A etapa isolada ainda inclui interrupcoes normais do RTOS; nao e bare metal.

## Analise e graficos

Use Python 3.12+ com `numpy`, `matplotlib` e `reportlab` instalados:

```powershell
python -m pip install numpy matplotlib reportlab
python tools/analyze.py resultados/AAAAMMDD_HHMMSS
python tools/make_report.py resultados/AAAAMMDD_HHMMSS
python tests/test_analysis.py
```

O script tambem aceita dependencias locais em `tools/python_deps`.
D fixo = 1,2 vezes o HWM da etapa 1. Igualdade cumpre o prazo.
HWM99 remove exatamente floor(0,01*N) maiores observacoes.
S e indefinido com menos de duas perdas. Rajada = pelo menos duas perdas
consecutivas; perdas isoladas sao contadas separadamente.
Janelas k=10,20,50 usam todas as posicoes validas, sem preenchimento nas bordas.
O criterio escolhido para o experimento D e (18,20); o menor D observado
que o satisfaz e o maximo do 18o menor tempo de cada janela de 20.
Listas completas de perdas, distancias, janelas e graficos ficam em `analise/`.

## Corretude e cobertura (experimento A)

```powershell
./tools/test_coverage.ps1
```

Requer GCC/gcov do MinGW (padrao: instalacao do CodeBlocks; parametro
`-CompilerBin` permite outro diretorio). A suite testa entrada vazia,
ponteiro invalido, tamanho fora do limite de frequencias, simbolo unico,
todos os 256 simbolos, centenas de tamanhos e cada ponto de falha de alocacao.
O mesmo huffman.c e incluido no teste, com substituicao somente dos alocadores
para injetar falhas. Os resultados de cobertura sao do host, nao do binario ESP32.
Nao se mede tempo do firmware com gcov ativado.

Resultado: 113/113 linhas, 71/74 resultados de desvios (95,95%). Os tres
resultados restantes pertencem a `!left && !right`: exigiriam left nulo e
right nao nulo, impossivel para a arvore binaria cheia criada pelo algoritmo.
Nao confundir `Branches executed: 100%` com `Taken at least once: 95.95%`.
Cobertura de linhas/desvios nao equivale a cobertura de todos os caminhos.

## Limitacoes e entrega

Uma campanha nao prova WCRT nem garante (m,k) para execucoes futuras.
A RAM reservada, alocador, ordem dos cenarios, interrupcoes e fases das tarefas
influenciam a medicao. Windows e os programas do PC apenas capturam a serial;
nao sao o SO onde os tempos de Huffman foram medidos.
O firmware termina apos a etapa 4; reinicie para nova campanha.
O relatorio gerado precisa ser lido e validado pelos integrantes, conforme
orientacao do enunciado. Preencha os RAs e renomeie o ZIP antes de entregar.
Repositorio: https://github.com/BazilioThiago/projeto-codigo-huffman-md


Teste automatizado do capturador (Python com pyserial): `python tests/test_capture.py`.
O arquivo pytest_hello_world.py e legado do template ESP-IDF; nao e a suite desta atividade.

Em outro computador, ative primeiro o terminal ESP-IDF; alternativamente passe -IdfPath e -PythonExecutable ao capturador. Para apenas capturar, basta Python com pyserial; nao depende de build/config.env nem de arquivos de log do monitor.

Para finalizar a identificacao, preencha `identificacao.json` e rode novamente:

```powershell
python tools/make_report.py resultados/AAAAMMDD_HHMMSS
python tools/package.py resultados/AAAAMMDD_HHMMSS
```

Com os RAs preenchidos, o empacotador usa automaticamente `STR_M3_RA1_RA2.zip`.
