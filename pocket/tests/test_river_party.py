"""Family room protocol and integration with the walk's touch menu."""
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

root=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(root/'graphics'),str(root/'shell')]
from river_party import RiverParty,PartyMenu
from river_walk import BUSHES,FOX


class FamilyWalkTests(unittest.TestCase):
    def test_shared_hunt_replay_wrong_code_and_timeout(self):
        server=RiverParty(True,5432,port=0)
        self.addCleanup(server.close)
        port=server.sock.getsockname()[1]
        def guest(code):
            client=RiverParty(False,code,'127.0.0.1',port)
            self.addCleanup(client.close)
            return client
        left,right,outsider=guest(5432),guest(5432),guest(7219)
        now=0.
        def tick(host=(0,0),a=(0,0),b=(0,0)):
            nonlocal now
            for _ in range(4):
                now+=.15
                for peer,pos in ((left,a),(right,b),(outsider,b),(server,host)):
                    peer.step(*pos,now)
        tick()
        self.assertEqual(len(left.roster),3)
        self.assertFalse(outsider.server)
        tick(a=BUSHES[0],b=BUSHES[0])
        self.assertEqual(left.trail.picked,{BUSHES[0]})
        tick(host=BUSHES[2],b=BUSHES[1]);tick(a=FOX)
        for peer in (server,left,right):
            self.assertEqual(peer.hearts,1);self.assertTrue(peer.trail.fed)
        right.restart=True;tick()
        for peer in (server,left,right):
            self.assertEqual(peer.round,2);self.assertFalse(peer.trail.picked)
        server.step(0,0,now+6)
        self.assertEqual(server.roster,{server.ident:(0,0)})

    def test_eight_seats_and_a_waiting_ninth_player(self):
        host=RiverParty(True,4321,port=0)
        self.addCleanup(host.close)
        guests=[]
        for i in range(8):
            client=RiverParty(False,4321,'127.0.0.1',host.sock.getsockname()[1])
            self.addCleanup(client.close)
            guests.append(client)
        for tick in range(5):
            for client in guests:client.step(0,0,tick*.2)
            host.step(0,0,tick*.2)
        self.assertEqual(len(host.roster),8)
        self.assertTrue(all(len(client.roster)==8 for client in guests[:7]))
        self.assertFalse(guests[-1].roster)

    def test_touch_keypad(self):
        from unittest.mock import patch
        view=SimpleNamespace(party=None)
        view.enter_party=lambda party:setattr(view,'party',party)
        menu=PartyMenu(view);menu.tap_xy(4,4)
        with patch('river_party.RiverParty',return_value='joined') as factory:
            for x,y in ((3,4),(11,4),(19,4),(3,6)):menu.tap_xy(x,y)
            self.assertEqual(factory.call_args.args[:2],(False,1234))
