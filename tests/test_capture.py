import csv, pathlib, sys, tempfile, unittest
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
from capture_serial import capture
class FakeSerial:
    def __init__(self,lines): self.lines=iter(lines)
    def __enter__(self): return self
    def __exit__(self,*args): pass
    def readline(self):
        item=next(self.lines)
        return item if isinstance(item,bytes) else (item+'\n').encode()
class CaptureTest(unittest.TestCase):
    def run_capture(self,lines,folder):
        with patch('capture_serial.serial.Serial',return_value=FakeSerial(lines)), patch('capture_serial.time.sleep'):
            return capture('TEST',folder)
    def test_complete_campaign(self):
        lines=[]
        for stage in range(1,5):
            lines += [f'=== INICIO_CSV_ETAPA_{stage} ===','ativacao,tempo_us']
            lines += [f'{i},123' for i in range(1,(10000 if stage==4 else 1000)+1)]
            lines += [f'=== FIM_CSV_ETAPA_{stage} ===']
        lines += ['CAMPANHA_CONCLUIDA']
        # A serial timeout may return half a CSV row, not a complete line.
        lines[2:3] = [b'1,', b'123\n']
        with tempfile.TemporaryDirectory() as folder:
            out=self.run_capture(lines,folder)
            self.assertTrue((out/'complete.json').exists())
            with (out/'etapa4.csv').open() as f: self.assertEqual(len(list(csv.DictReader(f))),10000)
    def test_reject_missing_samples(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError): self.run_capture(['=== INICIO_CSV_ETAPA_1 ===','ativacao,tempo_us','1,123','=== FIM_CSV_ETAPA_1 ==='],folder)
            self.assertFalse(list(pathlib.Path(folder).rglob('complete.json')))
    def test_reject_firmware_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(RuntimeError): self.run_capture(['ERRO,etapa=3,dropped=1'],folder)
            self.assertFalse(list(pathlib.Path(folder).rglob('complete.json')))
if __name__=='__main__': unittest.main()
