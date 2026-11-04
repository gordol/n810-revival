"""Nokia releases require microReticulum; portable desktop builds retain Python RNS."""
import json
from pathlib import Path


def native_required(root=None):
    root = Path(root) if root is not None else Path(__file__).resolve().parents[4]
    info = root / 'build-info.json'
    return info.is_file() and json.loads(info.read_text()).get('platform') == 'n810'


def require_stock_allowed():
    if native_required():
        raise ValueError('This Nokia release uses microReticulum and microLXMF; Python RNS/LXMF is desktop-only')
