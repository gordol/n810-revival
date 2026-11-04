"""Python RNS/LXMF loader for desktop sessions; excluded from Nokia packages."""


def load_stack():
    from backend_policy import require_stock_allowed
    require_stock_allowed()
    import sys
    from importlib.machinery import PathFinder,SourceFileLoader
    from importlib.util import LazyLoader
    class Interfaces:
        def find_spec(self,fullname,path=None,target=None):
            if not fullname.startswith('RNS.Interfaces.') or fullname in (
                    'RNS.Interfaces.Interface','RNS.Interfaces.LocalInterface'):
                return None
            spec=PathFinder.find_spec(fullname,path)
            if spec is not None and isinstance(spec.loader,SourceFileLoader):
                spec.loader=LazyLoader(spec.loader)
            return spec
    finder=Interfaces();sys.meta_path.insert(0,finder)
    try:
        import RNS
        import LXMF
        return RNS,LXMF
    finally:
        sys.meta_path.remove(finder)
