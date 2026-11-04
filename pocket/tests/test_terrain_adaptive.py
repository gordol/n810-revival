import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from terrain_adaptive import fractions

class AdaptiveTests(unittest.TestCase):
    def run_path(self,bound):
        return fractions(10000,1000,1000,144.39,4/3,lambda f:(f,0),bound)
    def test_deep_valley_prunes_without_loading_detail(self):
        points,stats=self.run_path(lambda a,b:100)
        self.assertEqual(stats['bound_queries'],1)
        self.assertEqual(stats['cleared_intervals'],1)
        self.assertEqual(len(points),33)
    def test_narrow_ridge_cannot_be_hidden_by_average(self):
        def bound(a,b):return 1100 if a[0]<=.501<=b[0] else 100
        points,stats=self.run_path(bound)
        self.assertGreater(stats['refined_intervals'],0)
        self.assertGreater(stats['unresolved_intervals'],0)
        self.assertTrue(any(abs(p-.501)<.002 for p in points))
    def test_unknown_terrain_never_prunes(self):
        _,stats=self.run_path(lambda a,b:None)
        self.assertEqual(stats['cleared_intervals'],0)
        self.assertGreater(stats['unresolved_intervals'],0)
    def test_fresnel_zone_triggers_refinement_below_sight_line(self):
        _,stats=self.run_path(lambda a,b:990)
        self.assertGreater(stats['refined_intervals'],0)

if __name__=='__main__':unittest.main()
