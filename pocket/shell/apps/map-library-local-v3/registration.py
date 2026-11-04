"""Optional descriptor; canonical Registry integration belongs to Runtime."""
from pathlib import Path
import importlib.util
import sys
import types


def create(host, resource_root, state_root=None, *, open_map=None, app_context=None):
    service = None
    use_service = open_map is None
    if app_context is not None:
        services = getattr(app_context, 'services', None)
        service = services.get('map-open') if callable(getattr(services, 'get', None)) else None
        callback = getattr(service, 'open_map', None)
        if use_service and callable(callback):
            open_map = callback
    if state_root is None:
        state_root = getattr(service, 'root', None)
    directory = Path(__file__).resolve().parent
    # A unique package name keeps this isolated app and its local backend apart
    # from other experiments without changing sys.path or a canonical module.
    name = '_pocket_map_library_local_v3'
    if name not in sys.modules:
        package = types.ModuleType(name)
        package.__path__ = [str(directory)]
        sys.modules[name] = package
    module_name = name+'.library_app'
    if module_name not in sys.modules:
        spec = importlib.util.spec_from_file_location(
            module_name, directory/'library_app.py')
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(module_name, None)
            raise
    app = sys.modules[module_name].LibraryApp(host, resource_root, state_root, open_map=open_map)
    bind_notice = getattr(service, 'bind_notice', None)
    if use_service and callable(bind_notice):
        try:
            unsubscribe = bind_notice(app.on_map_open_notice)
            if not callable(unsubscribe):
                raise TypeError('Map viewer notice subscription must return an unsubscribe callback')
            app._map_unsubscribe = unsubscribe
        except BaseException:
            app.close()
            raise
    return app


def descriptor():
    return dict(id='map-library', title='Map Library', factory=create,
                preferred_size=(80, 24), minimum_size=(40, 14),
                category='Maps', description='Prepare and import local map packs',
                uses=({'id': 'map-open', 'required': False},),
                resources=('experiments/map-drag-trial/regional-pack-v2/bake.py',),
                help=(('Local maps', ('Request a preset, then explicitly approve preparation.',
                                      'U: import an existing local pack without a preparation job.',
                                      'Import validates a published pack; it does not activate it.',
                                      'O: request opening an imported pack through the optional map viewer.')),))
