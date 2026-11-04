"""Explicit client-local draft transactions using the shared radio domain API."""
import copy
import hashlib
import importlib.util
from pathlib import Path


def module(name):
    root=Path(__file__).resolve().parent
    path=root/'vendor/packet-console'/name
    spec=importlib.util.spec_from_file_location(name.replace('-','_'),path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result


library=module('n810-radio-library.py')
profiles=module('n810-radio-profiles.py')


def fingerprint(path):
    try:return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:return None


class Drafts:
    def __init__(self,root):
        self.root=Path(root);self.documents={};self.original={};self.signatures={}
        self.reload()

    def reload(self):
        documents={};signatures={}
        for kind,owner in (('banks',library),('profiles',profiles)):
            path=self.root/(kind+'.json')
            documents[kind]=owner.read_saved(path)
            signatures[kind]=fingerprint(path)
        self.documents=documents;self.signatures=signatures;self.original=copy.deepcopy(documents)

    def dirty(self,kind):return self.documents[kind]!=self.original[kind]

    def initialize(self,kind):
        if self.documents[kind] is not None:return
        self.documents[kind]=dict(version=1,banks=[library.core_bank()]) if kind=='banks' else dict(version=1,profiles=profiles.defaults())

    def edit_bank(self,operation,**params):
        self.documents['banks']=library.edit(self.documents['banks'],operation,**params)

    def edit_profile(self,identity,changes):
        result=profiles.edit_profile(self.documents['profiles']['profiles'],identity,changes)
        self.documents['profiles']=dict(self.documents['profiles'],profiles=result)

    def discard(self,kind):self.documents[kind]=copy.deepcopy(self.original[kind])

    def save(self,kind):
        path=self.root/(kind+'.json')
        if fingerprint(path)!=self.signatures[kind]:raise ValueError('Saved file changed externally; reload before saving.')
        document=self.documents[kind]
        if document is None:raise ValueError('Create a local draft first.')
        # The established domain writer owns validation and private atomic save.
        if kind=='banks':library.save(path,copy.deepcopy(document))
        else:profiles.save(path,document['profiles'])
        self.signatures[kind]=fingerprint(path)
        self.documents[kind]=(library if kind=='banks' else profiles).read_saved(path)
        self.original[kind]=copy.deepcopy(self.documents[kind])
