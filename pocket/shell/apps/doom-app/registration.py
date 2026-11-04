"""Cheap Doom registration metadata: no engine/data/native imports at discovery."""
from pathlib import Path
import importlib.util

APP_ID='doom'
WINDOW_NAME='Doom / Freedoom'
HELP=(
    ('Play',('Arrows: walk / turn','W/S: walk; A/D: strafe','Space: fire; E: use doors','1–7: weapons; Tab: automap','Escape: game menu')),
    ('Window and focus',('Use desktop window controls to move, resize, hide or close.',
                         'Leaving game focus pauses play and releases held keys.',
                         'Close and reopen resumes this desktop session.',
                         'Press/release input supports simultaneous movement.',
                         'Keypress-only input retains inferred releases.')),
    ('Install',('DoomGeneric is the engine; Freedoom is the game data.',
                'Missing components are checked only when opening Doom.',
                'Build locally with apps/doom-app/build.py.',
                'R retries a failed launch. Audio is disabled.')),
)

def create(host,**options):
    path=Path(__file__).with_name('adapter.py')
    spec=importlib.util.spec_from_file_location('_current_world_doom_adapter',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    owner=module.DesktopDoom(host,**options)
    owner.help=HELP
    return owner

REGISTRATION={'id':'doom','title':WINDOW_NAME,'preferred_size':(82,27),'minimum_size':(22,10),
              'description':'Freedoom — keyboard game in a shared RGB viewport','category':'Games',
              'help':HELP,'factory':create,
              'resources':('build/doom-engine','build/bridge.so','vendor/freedoom-0.13.0/freedoom1.wad'),
              'resource_option':'root'}

def descriptor():
    """Detached descriptor normalized once by the shared runtime registry."""
    return dict(REGISTRATION)
