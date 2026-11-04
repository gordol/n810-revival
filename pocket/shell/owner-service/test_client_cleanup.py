import ast
from pathlib import Path
import selectors
import socket
import unittest


class CleanupTests(unittest.TestCase):
    def setUp(self):
        tree = ast.parse(Path(__file__).with_name('n810-aprs-feed.py').read_text())
        self.main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'main')
        drop = next(n for n in ast.walk(self.main) if isinstance(n, ast.FunctionDef) and n.name == 'drop')
        self.sel = selectors.DefaultSelector()
        self.client, self.peer = socket.socketpair()
        self.clients = {self.client: bytearray()}
        self.scope = dict(sel=self.sel, clients=self.clients, replay_clients=set(), controls={}, subscribers=set())
        exec(compile(ast.fix_missing_locations(ast.Module(body=[drop], type_ignores=[])), '<actual owner drop>', 'exec'), self.scope)
        self.sel.register(self.client, selectors.EVENT_READ)

    def tearDown(self):
        self.client.close()
        self.peer.close()
        self.sel.close()

    def test_double_drop_real_socket(self):
        self.scope['drop'](self.client)
        self.scope['drop'](self.client)
        self.assertEqual(self.client.fileno(), -1)
        self.assertEqual(self.clients, {})

    def test_returned_event_for_dropped_client_is_skipped(self):
        self.peer.send(b'queued event')
        queued = self.sel.select(timeout=1)
        self.assertEqual(len(queued), 1)
        self.scope['drop'](self.client)
        body = None
        for node in ast.walk(self.main):
            if not isinstance(node, ast.If) or not node.orelse:
                continue
            first = node.orelse[0]
            if (isinstance(first, ast.Assign) and isinstance(first.value, ast.Attribute)
                    and isinstance(first.value.value, ast.Name) and first.value.value.id == 'key'
                    and first.value.attr == 'fileobj'):
                body = node.orelse
                break
        self.assertIsNotNone(body)
        loop = ast.For(target=ast.Tuple(elts=[ast.Name(id='key', ctx=ast.Store()),
                                            ast.Name(id='events', ctx=ast.Store())], ctx=ast.Store()),
                       iter=ast.Name(id='queued', ctx=ast.Load()), body=body, orelse=[])
        self.scope.update(queued=queued, selectors=selectors)
        exec(compile(ast.fix_missing_locations(ast.Module(body=[loop], type_ignores=[])),
                     '<actual owner returned-event branch>', 'exec'), self.scope)
        self.assertEqual(self.clients, {})


if __name__ == '__main__':unittest.main()
