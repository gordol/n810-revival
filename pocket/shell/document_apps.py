"""Application-owned Reader/Library lifetimes and explicit command dispatch."""
import hashlib
import importlib.util
from pathlib import Path
import sys
import time
from native_documents import ReaderView,LibraryView


def domain_root(name):
    here=Path(__file__).resolve().parent
    return next((root for root in (here/'vendor/apps',)
                 if (root/'domains'/name/'__init__.py').is_file()),None)


def load_domain(name):
    if name not in ('reader','library'):raise ValueError('Unknown document domain')
    root=domain_root(name)
    if root is None:raise ImportError(name.capitalize()+' domain is not installed')
    key='_pocket_'+name+'_domain'
    if key not in sys.modules:
        path=root/'domains'/name/'__init__.py'
        spec=importlib.util.spec_from_file_location(key,path,submodule_search_locations=[str(path.parent)])
        module=importlib.util.module_from_spec(spec);sys.modules[key]=module
        try:spec.loader.exec_module(module)
        except Exception:sys.modules.pop(key,None);raise
    return sys.modules[key]


class DocumentApp:
    def __init__(self,model,view):
        self.model=model;self.view=view;self.closed=False;self.next_poll=0;self.query='';self.saved_only=False
        self.publish()

    def publish(self):
        options={'saved_only':self.saved_only} if isinstance(self.view,ReaderView) else {}
        self.view.update(self.model.snapshot(),self.model.search(self.query,**options))

    def command(self,action,*args):
        if self.closed:return
        if action=='search':self.query=args[0];self.publish();return
        if action=='saved_only':self.saved_only=not self.saved_only;self.view.saved_only=self.saved_only;self.publish();return
        try:
            result=self.dispatch(action,*args)
            if result is not None:self.view.notice=('Queued: ' if result.code=='accepted' else '')+result.message
        except (OSError,ValueError,RuntimeError) as error:self.view.notice=str(error)
        self.publish()

    def poll(self):
        if self.closed or not self.model.busy:return
        now=time.monotonic()
        if now<self.next_poll:return
        self.next_poll=now+.1
        if self.model.poll():
            self.view.notice='';self.publish()

    def poll_interval(self):return .1 if not self.closed and self.model.busy else None

    def close(self):
        if not self.closed:self.closed=True;self.model.close()


class ReaderApp(DocumentApp):
    def __init__(self,cache_root,*,model=None):
        self.domain=load_domain('reader')
        super().__init__(model if model is not None else self.domain.Reader(cache_root),ReaderView(self.command))

    def dispatch(self,action,*args):
        if action=='example':return self.model.import_local(domain_root('reader')/'domains/reader/fixtures/field-notes.rss')
        if action not in ('import_local','refresh','refresh_article','set_read','set_saved','load','cancel'):raise ValueError('Unknown Reader action')
        return getattr(self.model,action)(*args)


class LibraryApp(DocumentApp):
    def __init__(self,roots=(),*,model=None):
        self.domain=load_domain('library');self.roots=list(dict.fromkeys(str(root) for root in roots))
        super().__init__(model if model is not None else self.make_model(),LibraryView(self.command))

    def make_model(self):
        collections=tuple(self.domain.Collection(hashlib.sha256(root.encode()).hexdigest()[:16],Path(root).name or root,root) for root in self.roots)
        return self.domain.Library(collections)

    def dispatch(self,action,*args):
        if action=='add_root':
            if self.model.busy:raise RuntimeError('Wait for the active Library operation before changing folders')
            root=args[0].strip()
            if not root:raise ValueError('Enter a collection folder')
            if root in self.roots:return
            if len(self.roots)>=16:raise ValueError('Library supports up to16 configured folders')
            self.roots.append(root);previous=self.model
            try:self.model=self.make_model()
            except Exception:self.roots.pop();raise
            previous.close();self.view.notice='Folder configured for this session; choose Scan to index'
            return
        if action not in ('scan','open','cancel'):raise ValueError('Unknown Library action')
        return getattr(self.model,action)(*args)
