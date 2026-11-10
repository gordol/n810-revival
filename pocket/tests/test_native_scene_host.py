"""Native scene/damage preserves reference values and existing scheduling order."""
from array import array
from concurrent.futures import CancelledError
from unittest.mock import patch
import os,random,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from native_runtime import select
from native_cells import load
from native_scene import Damage,flux
from flux import reference_frame
from core import Host,Window
class NativeSceneTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path=os.environ.get('POCKET_TEST_NATIVE') or select(build=False)['library']
        if not path:raise unittest.SkipTest('native build unavailable')
        cls.lib=load(path)
        if not hasattr(cls.lib,'flux_surface'):raise unittest.SkipTest('native scenes unavailable')
    def test_damage_bounds_match_mutations_without_consuming_indices(self):
        self.assertTrue(hasattr(self.lib,'damage_bounds'))
        rng=random.Random(2420)
        for width,height in ((1,1),(7,9),(100,30)):
            damage=Damage(self.lib,width*height);expected=set()
            for step in range(160):
                values={rng.randrange(width*height) for _ in range(rng.randrange(20))}
                if step%3==0:
                    damage.difference_update(values);expected.difference_update(values)
                elif step%17==0:damage.clear();expected.clear()
                else:damage.update(values);expected.update(values)
                if expected:
                    xs=[i%width for i in expected];ys=[i//width for i in expected]
                    bounds=(min(xs),min(ys),max(xs)-min(xs)+1,max(ys)-min(ys)+1)
                else:bounds=(0,0,0,0)
                self.assertEqual(damage.bounds(width),bounds)
                self.assertEqual(set(damage),expected)
            for invalid in (0,width*height+1):
                with self.assertRaises(ValueError):damage.bounds(invalid)
    def test_flux_matches_reference_base_overlay_and_order(self):
        for w,h in ((1,1),(40,15),(100,29)):
            for ascii,step,density,glow,arms in ((False,0,1.,.15,2),(True,7,.5,0.,0),(False,41,4.,1.,4)):
                with self.subTest(view=(w,h),ascii=ascii,step=step):
                    a=reference_frame(w,h,step,ascii,density,glow,arms);b=flux(self.lib,w,h,step,ascii,density,glow,arms)
                    self.assertEqual(dict(a.base),dict(b.base));self.assertEqual(list(a.overlay.items()),list(b.overlay.items()))
    def test_damage_matches_sets_and_priority_order(self):
        rng=random.Random(709);d=Damage(self.lib,200);expected=set()
        for i in range(200):
            values=set(rng.sample(range(200),rng.randrange(80)))
            if i%4==0:d.update(values);expected.update(values)
            elif i%4==1:d.difference_update(array('I',values));expected.difference_update(values)
            elif i%4==2:d.intersection_update(Damage(self.lib,200,values));expected.intersection_update(values)
            else:d.mark(20,2,3,8,4);expected.update(y*20+x for y in range(3,7) for x in range(2,10))
            self.assertEqual(set(d),expected);self.assertEqual(len(d),len(expected))
            priority=expected&set(rng.sample(range(200),60));p=Damage(self.lib,200,priority)
            for budget in (0,7,64,160,300):
                a,b=sorted(priority),sorted(expected-priority);wanted=[];u=v=0
                while len(wanted)<budget and (u<len(a) or v<len(b)):
                    take=min(48 if v<len(b) else 64,budget-len(wanted));wanted.extend(a[u:u+take]);u+=min(take,len(a)-u)
                    take=min(64 if u>=len(a) else 16,budget-len(wanted));wanted.extend(b[v:v+take]);v+=min(take,len(b)-v)
                self.assertEqual(list(d.take(budget,p)),wanted)
    def test_scene_size_accounting_never_fetches_native_cells(self):
        scene=flux(self.lib,100,29,1,False,1.,.15,2)
        with patch.object(type(scene.base),'__getitem__',side_effect=AssertionError('Per-cell read')):
            self.assertEqual(len(scene),2900)
    def test_flux_phase_reuse_preserves_fractional_and_extreme_times(self):
        rng=random.Random(304)
        for step in (.2,.6,1.4,17.2,1000.2,90000000.,1e12,-1e12):
            w,h=rng.randrange(20,90),rng.randrange(12,35)
            density,glow,arms=rng.uniform(.5,4),rng.random(),rng.randrange(5)
            a=reference_frame(w,h,step,False,density,glow,arms)
            b=flux(self.lib,w,h,step,False,density,glow,arms)
            self.assertEqual(list(a.overlay.items()),list(b.overlay.items()),(w,h,step))
    def test_native_diff_and_output_match_reference_for_consecutive_frames(self):
        a=Host(40,15,[]);b=Host(40,15,[])
        for h in (a,b):
            h.background_enabled=False;h.shadow_enabled=False;h.animate=False;self.assertTrue(h.enable_native(os.environ.get('POCKET_TEST_NATIVE') or select(build=False)['library']))
        for step in range(4):
            a.background(a.scene_cells(reference_frame(40,15,step)))
            b.background(b.scene_cells(flux(self.lib,40,15,step,False,1.,.15,2)))
            self.assertEqual(set(a.damage),set(b.damage))
            aa=[];bb=[]
            while a.damage:aa.append(a.flush(64))
            while b.damage:bb.append(b.flush(64))
            self.assertEqual(aa,bb)
    def test_native_bounded_redraw_matches_64_cell_batches(self):
        path=os.environ.get('POCKET_TEST_NATIVE') or select(build=False)['library']
        for seconds in (0.,1.):
            a,b=Host(40,15,[]),Host(40,15,[])
            for h in (a,b):
                h.background_enabled=False;h.shadow_enabled=False;h.animate=False
                self.assertTrue(h.enable_native(path))
                h.background(h.scene_cells(flux(self.lib,40,15,7,False,1.,.15,2)))
                h.ui_damage.update(range(300,500))
            expected=[];actual=[];changed_a=changed_b=0
            while a.damage:
                output,changed,count=a.flush(64);expected.append(output);changed_a+=changed
            while b.damage:
                before=len(b.damage)
                output,changed,count=b.flush(600,max_seconds=seconds)
                self.assertGreater(count,0)
                self.assertEqual(len(b.damage),before-count)
                if seconds==0.:self.assertLessEqual(count,64)
                actual.append(output);changed_b+=changed
            self.assertEqual(''.join(actual),''.join(expected))
            self.assertEqual(changed_a,changed_b)
    def test_expired_scene_admission_budget_keeps_bounded_native_progress(self):
        path=os.environ.get('POCKET_TEST_NATIVE') or select(build=False)['library']
        for seconds,ui,expected in ((.012,False,.003),(0.,False,0.),(.012,True,0.),(.012,'late',0.)):
            host=Host(40,15,[]);host.shadow_enabled=False;host.animate=False
            self.assertTrue(host.enable_native(path));host.desktop_effects=['flux']*3;host.background_enabled=True
            host._flux_external_budget=True;host.tick=lambda **kwargs:None
            host.background(host.scene_cells(flux(self.lib,40,15,7,False,1.,.15,2)))
            host.ui_damage.clear()
            if ui=='late':host.tick=lambda **kwargs:host.ui_damage.add(0)
            elif ui:host.ui_damage.add(0)
            actual=host._native.flush;budgets=[]
            def observe(*args,**kwargs):
                budgets.append(kwargs['max_seconds']);return actual(*args,**kwargs)
            clock=iter(range(1000))
            with patch.object(host._native,'flush',side_effect=observe),patch('core.time.monotonic',side_effect=lambda:next(clock)):
                host.flush(600,max_seconds=seconds)
            self.assertEqual(budgets,[expected])
            while host.damage:host.flush(600,max_seconds=None)
            reference=Host(40,15,[]);reference.background_enabled=False;reference.shadow_enabled=False;reference.animate=False
            self.assertTrue(reference.enable_native(path))
            reference.background(reference.scene_cells(flux(self.lib,40,15,7,False,1.,.15,2)))
            while reference.damage:reference.flush(600,max_seconds=None)
            self.assertEqual(list(host.front),list(reference.front))

    def test_cancellation_does_not_publish_or_corrupt_a_frame(self):
        def stop():raise CancelledError()
        with self.assertRaises(CancelledError):self.lib.nebula(40,15,False,stop)
        base=self.lib.nebula(40,15,False,lambda:None)
        with self.assertRaises(CancelledError):self.lib.flux_surface(40,15,0,False,1.,.15,2,base,stop)
        self.assertEqual(dict(flux(self.lib,40,15,1,False,1.,.15,2)),dict(reference_frame(40,15,1)))
if __name__=='__main__':unittest.main()
