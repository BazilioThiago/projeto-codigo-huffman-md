"""Renderiza paginas do relatorio para revisao visual local (dependencia: pypdfium2)."""
import pathlib,sys
sys.path.insert(0,str(pathlib.Path(__file__).parent/'python_deps'))
import pypdfium2 as pdfium
from PIL import Image,ImageOps,ImageDraw
out=pathlib.Path('tmp/pdfs'); out.mkdir(parents=True,exist_ok=True)
doc=pdfium.PdfDocument('output/pdf/relatorio_huffman.pdf')
thumbs=[]
for i,page in enumerate(doc):
    im=page.render(scale=1.5).to_pil().convert('RGB')
    im.save(out/f'pagina_{i+1}.png')
    tile=Image.new('RGB',(450,660),'#dde5eb'); im.thumbnail((430,620)); tile.paste(im,((450-im.width)//2,20)); ImageDraw.Draw(tile).text((15,640),f'Pagina {i+1}',fill='black'); thumbs.append(tile)
sheet=Image.new('RGB',(450*2,660*((len(thumbs)+1)//2)),'white')
for i,im in enumerate(thumbs): sheet.paste(im,((i%2)*450,(i//2)*660))
sheet.save(out/'contato.png'); print(f'{len(doc)} paginas renderizadas')
assert len(doc)==8, f'Esperado 8 paginas, recebido {len(doc)}'
