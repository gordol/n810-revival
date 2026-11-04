"""Lazy descriptor; the Runtime owner controls canonical menu registration."""
from pathlib import Path
import importlib.util

class UnavailableWildlife:
    """Normal readable form when an optional asset/dependency is unavailable."""
    def __init__(self,error):
        self.width=96;self.height=32;self.error=str(error)
    def open(self):return True
    def lines(self):
        return ('Wildlife could not open.',self.error[:self.width],
                'The optional wildlife assets or dependencies are unavailable.',
                'Close this window and try again after they are restored.')
    def spans(self):return ()
    def layer(self):return None
    def key(self,key):return False
    def poll(self):return None
    def poll_interval(self):return None
    def on_close(self):pass
    def on_focus(self,*args):pass
    def on_visibility(self,*args):pass
    def set_active(self,active):pass
    def close(self):pass

def create(host,**options):
    import sys
    directory=Path(__file__).resolve().parent
    if str(directory) not in sys.path:sys.path.insert(0,str(directory))
    try:
        spec=importlib.util.spec_from_file_location('_landscape_wildlife',directory/'wildlife_app.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module.Wildlife(host,**options)
    except (ImportError,OSError) as error:
        return UnavailableWildlife(error)

def descriptor():
    return dict(id='wildlife',title='Wildlife',preferred_size=(98,34),minimum_size=(28,14),category='Experiments',
                description='Photo-referenced marmot and eagle with retained glyph surfaces',
                help=(('Wildlife',('Tab animal; Space pause; arrows view; O obstacle; R reset.',)),),factory=create)
