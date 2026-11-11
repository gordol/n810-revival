"""Uncreated registry slots must not add per-redraw readiness/deadline work."""
from pathlib import Path
import selectors,socket,sys,unittest
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
from app_registry import LazyApplication,instantiated_forms
from app_readiness import AppReadiness
class InstantiatedFormsTests(unittest.TestCase):
 def lazy(self,kind=LazyApplication):
  return kind(SimpleNamespace(),SimpleNamespace(preferred_size=(24,8)),SimpleNamespace())
 def test_only_exact_uncreated_wrappers_are_skipped(self):
  class Custom(LazyApplication):
   def poll_interval(self):return .1
  lazy=self.lazy();custom=self.lazy(Custom);ordinary=SimpleNamespace()
  forms={'lazy':lazy,'custom':custom,'ordinary':ordinary}
  self.assertEqual(instantiated_forms(forms),(('custom',custom),('ordinary',ordinary)))
  lazy.owner=object()
  self.assertEqual(instantiated_forms(forms),tuple(forms.items()))
 def test_owner_creation_replacement_and_retirement_refresh_real_selector(self):
  selector=selectors.DefaultSelector();self.addCleanup(selector.close)
  ready=AppReadiness(selector);self.addCleanup(ready.close)
  a,aw=socket.socketpair();b,bw=socket.socketpair()
  for sock in (a,aw,b,bw):self.addCleanup(sock.close)
  class Owner:
   def __init__(self,sock):self.sock=sock;self.seen=[]
   def readiness_sources(self):return ((self.sock,self.event),)
   def event(self):self.seen.append(self.sock.recv(1))
  lazy=self.lazy();forms={'app':lazy}
  def sync():ready.sync(form for _,form in instantiated_forms(forms))
  sync();self.assertEqual(ready.sources,{})
  one=Owner(a);lazy.owner=one;sync();aw.send(b'a');selector.select(.1)[0][0].data.callback();self.assertEqual(one.seen,[b'a'])
  two=Owner(b);lazy.owner=two;sync();self.assertNotIn(a.fileno(),ready.sources)
  bw.send(b'b');selector.select(.1)[0][0].data.callback();self.assertEqual(two.seen,[b'b'])
  lazy.owner=None;sync();self.assertEqual(ready.sources,{})
if __name__=='__main__':unittest.main()
