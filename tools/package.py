"""Empacota somente fontes, evidencias e relatorio; nao inclui SDK nem dependencias locais."""
import hashlib, json, pathlib, re, sys, zipfile
root=pathlib.Path(__file__).resolve().parents[1]
folder=pathlib.Path(sys.argv[1]).resolve()
if not (folder/'complete.json').exists(): raise SystemExit('Campanha incompleta')
identity=json.loads((root/'identificacao.json').read_text(encoding='utf-8-sig'))
ras=[p['ra'].strip() for p in identity['integrantes']]
suffix='_'.join(re.sub(r'[^A-Za-z0-9_-]','',ra) for ra in ras) if all(ras) else 'Thiago_Bazilio_Guilherme_Santana_RAs_pendentes'
out=root/'output'/f'STR_M3_{suffix}.zip'
files=[root/n for n in ['identificacao.json','README.md','CMakeLists.txt','sdkconfig.defaults','Atividade.pdf']]
files += list((root/'main').glob('*'))
files += [p for p in (root/'tools').iterdir() if p.suffix in ('.py','.ps1','.txt')]
files += list((root/'tests').glob('*.py')) + list((root/'tests').glob('*.c'))
files += [p for p in folder.rglob('*') if p.is_file()]
files += list((root/'resultados'/'cobertura').glob('*.gcov'))+list((root/'resultados'/'cobertura').glob('*.txt'))
files += [root/'resultados'/'processos_host.txt',root/'output'/'pdf'/'relatorio_huffman.pdf']
with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
    for p in files:
        if p.is_file(): z.write(p,p.relative_to(root))
with zipfile.ZipFile(out) as z:
    assert z.testzip() is None
    print(f'{len(z.namelist())} arquivos; ZIP verificado: {out}')
print('SHA256:',hashlib.sha256(out.read_bytes()).hexdigest())
