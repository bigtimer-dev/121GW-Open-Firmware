"""Checks of the custom-build emulator fixes E-01..E-05 (emulator/ui/server.py, emulator/app.py) with a stub emulator:
no firmware runs, IMAGE is only used as upload data.  E-01 speed NaN / inf / <= 0 refused; E-02 Host and Origin checks;
E-03 negative / non-numeric Content-Length and the 64 KiB /input cap; E-04 upload names '.' / '..'; E-05 static paths.

    python -I emulator/scripts/test_custom_server.py [image]   default firmware/build/EEVBlog.bin
"""
import http.client
import os
import socket
import sys
import threading
import types

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
IMAGE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, 'firmware', 'build', 'EEVBlog.bin')
sys.path.insert(0, os.path.join(REPO, 'emulator'))
sys.dont_write_bytecode = True
import app                        # noqa: E402
from ui import server             # noqa: E402

fails = []


def check(name, ok, detail=''):
    print('  %-62s %s %s' % (name, 'ok' if ok else 'FAIL', detail), flush=True)
    if not ok:
        fails.append(name)


class Stub:
    def __init__(self):
        self.cmds = []

    def snapshot(self):
        return {'ok': 1}

    def command(self, c):
        if 'speed' in c:
            app.check_speed(c['speed'])
        self.cmds.append(c)


emu = Stub()
s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()
httpd = server.serve(emu, port)


def req(method, path, body=b'', headers=None, timeout=3):
    c = http.client.HTTPConnection('127.0.0.1', port, timeout=timeout)
    c.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
    h = {'Host': '127.0.0.1:%d' % port, 'Content-Length': str(len(body))}
    h.update(headers or {})
    for k, v in h.items():
        if v is not None:
            c.putheader(k, v)
    c.endheaders()
    if body:
        c.send(body)
    try:
        r = c.getresponse()
        return r.status, r.read()
    except socket.timeout:
        return 'timeout', b''


st, _ = req('POST', '/input', b'{"key":"RANGE","down":true}',
            {'Content-Type': 'application/x-www-form-urlencoded'})
check('curl-style POST /input (no Origin) accepted', st == 200 and emu.cmds[-1] == {'key': 'RANGE', 'down': True}, st)
st, _ = req('POST', '/input', b'{"dial":5}', {'Origin': 'http://127.0.0.1:%d' % port})
check('own page POST /input (same Origin) accepted', st == 200, st)
st, _ = req('POST', '/input', b'{"dial":5}', {'Host': 'localhost:%d' % port, 'Origin': 'http://localhost:%d' % port})
check('own page via localhost accepted', st == 200, st)
n = len(emu.cmds)
st, _ = req('POST', '/input', b'{"dial":0}', {'Origin': 'https://evil.example', 'Content-Type': 'text/plain'})
check('cross-origin POST /input refused (403), no command run', st == 403 and len(emu.cmds) == n, st)
st, _ = req('POST', '/input', b'{"dial":0}', {'Origin': 'null'})
check('Origin null (sandboxed frame) refused', st == 403, st)
st, _ = req('GET', '/state', headers={'Host': 'evil.example:%d' % port})
check('DNS rebinding Host refused on GET /state', st == 403, st)
st, _ = req('POST', '/input', b'', {'Content-Length': '-1'})
check('negative Content-Length: 400 at once (no wait for EOF)', st == 400, st)
st, _ = req('POST', '/firmware', b'', {'Content-Length': '-5', 'X-121GW': 'firmware'})
check('negative Content-Length on /firmware: 400', st == 400, st)
st, _ = req('POST', '/input', b'', {'Content-Length': 'abc'})
check('non-numeric Content-Length: 400', st == 400, st)
st, _ = req('POST', '/input', b'', {'Content-Length': str(1 << 20)})
check('oversized /input body refused before reading', st == 400, st)
st, _ = req('POST', '/input', b'{"speed":"nan"}')
check('speed NaN refused (400)', st == 400, st)
st, _ = req('POST', '/input', b'{"speed":-1}')
check('speed -1 refused (400)', st == 400, st)
st, _ = req('POST', '/input', b'{"speed":2.5}')
check('speed 2.5 accepted', st == 200, st)
st, _ = req('GET', '/')
check('GET / serves the page', st == 200, st)
st, _ = req('GET', '/..%2fapp.py')
check('path traversal /..%2fapp.py refused (404)', st == 404, st)

print('load_app names')
up = []


class FakeEmu:
    lock = threading.Lock()

    def power_cycle(self):
        up.append(self.app_path)


fe = FakeEmu()
data = open(IMAGE, 'rb').read()
for name, want in (('..', 'firmware.bin'), ('.', 'firmware.bin'), ('', 'firmware.bin'), ('../../x.bin', 'x.bin'),
                   ('my fw.bin', 'my_fw.bin')):
    app.Emulator.load_app(fe, data, name)
    got = os.path.basename(fe.app_path)
    check('load_app(%r) -> %r inside the upload dir' % (name, want),
          got == want and os.path.dirname(fe.app_path) == fe._upload_dir and os.path.isfile(fe.app_path), got)
httpd.shutdown()
print('RESULT', 'FAIL: ' + ', '.join(fails) if fails else 'ALL PASS', flush=True)
sys.exit(1 if fails else 0)
