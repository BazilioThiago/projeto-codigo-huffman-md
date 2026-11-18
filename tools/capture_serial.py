import argparse, csv, datetime, hashlib, json, pathlib, re, time
import serial

def capture(port, output, timeout=600):
    folder = pathlib.Path(output) / datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    folder.mkdir(parents=True, exist_ok=False)
    root = pathlib.Path(__file__).resolve().parents[1]
    tracked = ['main/main.c','main/huffman.c','main/huffman.h','sdkconfig','build/projeto-codigo-huffman-md.bin']
    hashes = {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in tracked if (root/name).exists()}
    (folder/'provenance.json').write_text(json.dumps({'sha256':hashes},indent=2),encoding='utf-8')
    if (root/'sdkconfig').exists(): (folder/'sdkconfig.snapshot').write_bytes((root/'sdkconfig').read_bytes())
    print(f'Captura: {folder.resolve()}', flush=True)
    stage = None
    rows = []
    completed = []
    with serial.Serial(port, 115200, timeout=1) as dev, (folder/'serial.log').open('w', encoding='utf-8') as log:
        dev.dtr = False
        dev.rts = True
        time.sleep(.1)
        dev.rts = False
        pending = b''
        lines_logged = 0
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            pending += dev.readline()
            if not pending.endswith(b'\n'): continue
            line = pending.decode('utf-8', errors='replace').strip()
            pending = b''
            if not line: continue
            log.write(line+'\n')
            lines_logged += 1
            if lines_logged % 100 == 0: log.flush()
            if any(s in line for s in ('ERRO,', 'Guru Meditation', 'abort() was called', 'assert failed', 'Task watchdog got triggered')):
                raise RuntimeError(line)
            begin = re.fullmatch(r'=== INICIO_CSV_ETAPA_(\d) ===', line)
            end = re.fullmatch(r'=== FIM_CSV_ETAPA_(\d) ===', line)
            if begin:
                if stage is not None: raise ValueError('Bloco interrompido')
                stage=int(begin[1]); rows=[]
            elif end:
                if stage != int(end[1]) or stage in completed: raise ValueError('Etapa invalida')
                expected = 10000 if stage == 4 else 1000
                if len(rows) != expected: raise ValueError(f'Esperado {expected}, recebido {len(rows)}')
                with (folder/f'etapa{stage}.csv').open('w',newline='') as f:
                    w=csv.writer(f); w.writerow(['ativacao','tempo_us']); w.writerows(rows)
                completed.append(stage)
                print(f'Etapa {stage}: {len(rows)} amostras salvas.',flush=True)
                stage=None
            elif stage is not None and line != 'ativacao,tempo_us':
                a,t=line.split(','); a=int(a); t=float(t)
                if a != len(rows)+1 or not 0 < t < 2**32: raise ValueError('Amostra invalida')
                rows.append((a,t))
            elif line.startswith(('META,','MEDINDO_')): print(line,flush=True)
            elif line == 'CAMPANHA_CONCLUIDA':
                if completed != [1,2,3,4]: raise ValueError('Campanha incompleta')
                (folder/'complete.json').write_text(json.dumps({'port':port,'baud':115200,'stages':completed},indent=2))
                return folder
        raise TimeoutError('Campanha incompleta: tempo limite excedido')

if __name__ == '__main__':
    p=argparse.ArgumentParser(); p.add_argument('--port',default='COM3'); p.add_argument('--output',default='resultados')
    args=p.parse_args()
    try:
        capture(args.port,args.output)
    except serial.SerialException as exc:
        p.exit(1, f'Falha na porta {args.port}: {exc}\nFeche o monitor do VS Code e outros leitores da porta antes de executar.\n')
    except (RuntimeError, ValueError, TimeoutError) as exc:
        p.exit(1, f'Campanha rejeitada: {exc}\nOs dados parciais e o log foram preservados; nao use esta execucao na analise.\n')
