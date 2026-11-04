"""Keep one CLI declaration, constructing argparse actions only when needed."""
import argparse
import sys


class Arguments:
    def __init__(self,full=False):
        self.options=[]
        self.groups=[]
        self.full=full

    def add_argument(self,name,**options):
        self.options.append((name,options,None))

    def add_mutually_exclusive_group(self):
        group=len(self.groups)
        self.groups.append(group)
        return _Group(self,group)

    def _parser(self,selected=None):
        parser=argparse.ArgumentParser()
        groups=[parser.add_mutually_exclusive_group() for _ in self.groups]
        for name,options,group in self.options:
            if selected is None or name in selected:
                (parser if group is None else groups[group]).add_argument(name,**options)
        return parser

    def parse_args(self,argv=None):
        argv=list(sys.argv[1:] if argv is None else argv)
        known={name for name,_,_ in self.options}
        selected={arg.split('=',1)[0] for arg in argv if arg.startswith('-')}
        # argparse owns help, abbreviations, unknown switches and unusual values.
        # Its complete parser also supplies error messages and complete usage.
        if self.full or selected-known:
            return self._parser().parse_args(argv)
        defaults={}
        for name,options,_ in self.options:
            value=options.get('default',False if options.get('action')=='store_true' else None)
            if name not in selected and isinstance(value,str) and options.get('type'):
                try:value=options['type'](value)
                except (ValueError,TypeError):return self._parser().parse_args(argv)
            defaults[name[2:].replace('-','_')]=value
        parser=self._parser(selected)
        # Errors must show all options, not just this launch's selected subset.
        parser.error=self.error
        return parser.parse_args(argv,argparse.Namespace(**defaults))

    def error(self,message):
        self._parser().error(message)


class _Group:
    def __init__(self,owner,index):self.owner,self.index=owner,index
    def add_argument(self,name,**options):self.owner.options.append((name,options,self.index))
