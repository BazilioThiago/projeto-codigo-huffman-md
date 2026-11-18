import sys, pathlib, unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
from analyze import deadline_stats, minimum_deadline
class AnalysisTest(unittest.TestCase):
    def test_losses_and_windows(self):
        v=[1]*60
        for i in (1,2,5,24): v[i-1]=9
        s,w=deadline_stats(v,5)
        self.assertEqual(s['losses'],[1,2,5,24])
        self.assertEqual(s['distances'],[1,3,19])
        self.assertEqual(s['skip'],1)
        self.assertEqual(s['bursts'],[[1,2]])
        self.assertEqual(s['isolated'],2)
        self.assertEqual(s['mk']['20'],[17,20])
        self.assertEqual(w[20][0],3)
    def test_equal_deadline_and_no_losses(self):
        s,_=deadline_stats([5]*60,5)
        self.assertEqual(s['on_time_pct'],100)
        self.assertIsNone(s['skip'])
        self.assertEqual(s['mk']['50'],[50,50])
    def test_minimal_deadline(self):
        self.assertEqual(minimum_deadline(list(range(1,61))),58)
        s,_=deadline_stats(list(range(1,61)),57)
        self.assertLess(s['mk']['20'][0],18)
if __name__=='__main__': unittest.main()
