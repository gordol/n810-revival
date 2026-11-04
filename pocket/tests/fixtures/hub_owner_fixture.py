"""Deterministic firmware replies behind the production owner socket and PTYs."""
import argparse,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'shell'))
sys.path.insert(0,str(ROOT/'tests'))
from test_htit_hub_owner import FakeLink
from vendor.apps.domains.meshcore.hub_owner import HubOwner,_server
from vendor.apps.domains.meshcore.hub_session import HubSession
p=argparse.ArgumentParser()
for name in ('socket','state','station','port'):p.add_argument('--'+name,required=True)
p.add_argument('--ready-fd',type=int)
a=p.parse_args()
def factory(state,station):
    return HubOwner(state,station,a.port,session_factory=lambda port,publish:HubSession(port,publish,link_factory=FakeLink))
_server.serve(a.socket,a.state,a.station,factory,a.ready_fd)
