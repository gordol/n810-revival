"""Temporary loopback bridge between Pocket and its bundled offline map picker."""
from hmac import compare_digest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
import queue
import secrets
import subprocess
import sys
import threading
import webbrowser


ASSETS = Path(__file__).with_name('world_picker')
FILES = {'':'text/html','picker.js':'text/javascript','picker.css':'text/css','world.json':'application/json'}


def valid_bounds(values):
    return (isinstance(values,(tuple,list)) and len(values)==4
            and all(type(n) in (int,float) and math.isfinite(n) for n in values)
            and -180 <= values[0] < values[2] <= 180 and -90 < values[1] < values[3] < 90)


class Picker:
    def __init__(self, bounds, wakeup=None):
        self.result = queue.SimpleQueue()
        self.wakeup = wakeup
        self.prefix = '/'+secrets.token_urlsafe(24)+'/'
        picker = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def send_data(self, data, mime):
                self.send_response(200)
                self.send_header('Content-Type', mime+'; charset=utf-8')
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control','no-store')
                self.send_header('Referrer-Policy','no-referrer')
                self.send_header('Content-Security-Policy',"default-src 'self'; frame-ancestors 'none'; object-src 'none'")
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                name=self.path[len(picker.prefix):]
                if self.headers.get('Host')!=picker.host or not self.path.startswith(picker.prefix):
                    return self.send_error(404)
                if name=='selection':
                    return self.send_data(json.dumps(bounds if valid_bounds(bounds) else None).encode(),'application/json')
                if name not in FILES:
                    return self.send_error(404)
                self.send_data((ASSETS/(name or 'index.html')).read_bytes(),FILES[name])

            def do_POST(self):
                if (not compare_digest(self.path,picker.prefix+'selection') or self.headers.get('Host')!=picker.host
                        or self.headers.get('Origin')!='http://'+picker.host):
                    return self.send_error(403)
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=256:raise ValueError()
                    values=json.loads(self.rfile.read(size))
                    if not valid_bounds(values):raise ValueError()
                except (ValueError,OverflowError):
                    return self.send_error(400)
                self.send_data(b'{}','application/json')
                picker.result.put(values)
                if picker.wakeup:picker.wakeup()

        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.host='127.0.0.1:'+str(self.server.server_port)
        self.url='http://'+self.host+self.prefix
        threading.Thread(target=self.server.serve_forever,kwargs={'poll_interval':.05},daemon=True).start()

    def launch(self):
        if os.environ.get('POCKET_TERMUX')=='1':
            print('Pocket world map:', self.url, file=sys.stderr, flush=True)
            subprocess.run(['termux-open-url',self.url],check=True,timeout=3)
        elif not webbrowser.open(self.url):
            raise OSError('Could not open your browser')

    def close(self):
        self.wakeup=None
        self.server.shutdown()
        self.server.server_close()
