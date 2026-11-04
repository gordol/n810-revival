"""Shared local entity actions. Packet data never supplies executable actions."""
from collections import namedtuple


class EntityRef(namedtuple('EntityRef','kind key payload',defaults=(None,))):
    __slots__=()
    kind:str
    key:str
    payload:object
    def __new__(cls,kind,key,payload=None):
        if kind not in ('station','channel','observation','map-point','repeater') or not isinstance(key,str) or not key or len(key)>200:raise ValueError('Invalid entity reference')
        return super().__new__(cls,kind,key,payload)
    def __eq__(self,other):
        if type(other) is not type(self):return False
        return (self.kind,self.key)==(other.kind,other.key)
    def __ne__(self,other):
        value=self.__eq__(other)
        return NotImplemented if value is NotImplemented else not value
    def __hash__(self):return hash((self.kind,self.key))
    def __repr__(self):return f'EntityRef(kind={self.kind!r}, key={self.key!r})'


class ContextActions:
    def __init__(self):self.handlers={}
    def register(self,kind,label,handler,available=None):
        if kind not in ('station','channel','observation','map-point','repeater') or not callable(handler):raise ValueError('Invalid local action')
        self.handlers.setdefault(kind,[]).append((label,handler,available))
    def entries(self,entities):
        actions=[]
        for entity in entities:
            if not isinstance(entity,EntityRef):continue
            for label,handler,available in self.handlers.get(entity.kind,()):
                if available is not None and not available():continue
                suffix=entity.key if entity.kind=='station' else (entity.payload or {}).get('label','') if entity.kind=='map-point' else ''
                title=label+(' · '+suffix if suffix else '')
                actions.append((title,lambda handler=handler,entity=entity:handler(entity)))
        return actions
