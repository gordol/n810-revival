"""Offline manuals; loading topic data does not load the browser UI."""
def __getattr__(name):
    if name=='ManualBrowser':
        from .browser import ManualBrowser
        return ManualBrowser
    raise AttributeError(name)
