"""Local web UI for the 121GW emulator (Python standard library only).

GET  /               front panel page
GET  /assets/...     static assets (LCD layers, bit map)
GET  /state          JSON snapshot: LCD RAM, outputs, run state, recent log lines (fields: emulator/API.md)
POST /input          JSON command: {"key": name, "down": bool} | {"dial": position} |
                     {"jack": name, "plugged": bool} | {"run": bool} | {"reset": true} | {"speed": x} |
                     {"analog": "PA4"|"PA5", "volts": v} | {"battery": B+ volts (PA5 via R69/R70)} |
                     {"input": {"kind": "open"|"V"|"A"|"ohm"|"Hz"|"F"|"degC"|"diode"|"VA", "value": x,
                                "ac": bool, "freq": f, "duty": d, "width": s, "dc": v, "amps": a, "board": t}} |
                     {"environment": {"pickup_hz": 50|60, "pickup_v": v, "coupling_pf": c, "drift": d}} |
                     {"sdcard": bool} | {"sysreset": true} | {"firmware": "2_fast"|"1_like_v2.05"} (a release build, fetched on demand)
                     (stimulus fields: emu/frontend.py module docstring; app.py Emulator.command; all: emulator/API.md)
POST /firmware       run the application image in the request body (raw bytes, at most 1 MiB; the file name in the header
                     "X-121GW-File"); needs the request header "X-121GW: firmware" for the reason given for /quit;
                     a file that is not an application image is refused with the reasons (app.check_app_image)
POST /quit           stop the emulator process (needs the request header "X-121GW: quit", which a web page of another
                     origin cannot send without a CORS preflight that this server does not answer)
Every request must name this server in its Host header (127.0.0.1, localhost or [::1] with the port: no DNS rebinding),
and a POST that carries an Origin header (every browser POST) must come from this server's own page (403 otherwise):
a web page of another origin cannot drive /input with a simple request.  curl and scripts send no Origin.  A request
body has a valid Content-Length (not negative; /input at most 64 KiB).
The emulator object passed to serve() must provide snapshot() and command(dict); it runs in its
own thread and is shared with scripted tests, so the page always shows the machine under test.
"""
import json, os, threading
from urllib.parse import unquote
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
TYPES = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css',
         '.svg': 'image/svg+xml', '.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg'}


def make_handler(emu, lan_host=None):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype):
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _hosts(self):
            port = self.server.server_address[1]
            hosts = {f'127.0.0.1:{port}', f'localhost:{port}', f'[::1]:{port}'}
            if lan_host:                                 # fork: --host ADDRESS (opt-in, the address named only)
                hosts.add(f'{lan_host}:{port}')
            return hosts

        def _local_host(self):
            host = self.headers.get('Host')
            return host is None or host.lower() in self._hosts()

        def _same_origin(self):
            origin = self.headers.get('Origin')
            return origin is None or origin.lower() in {'http://' + h for h in self._hosts()}

        def _length(self):
            """Content-Length as an int, None when it is missing a number or negative (read(-1) waited for EOF)."""
            try:
                n = int(self.headers.get('Content-Length', 0))
            except ValueError:
                return None
            return n if n >= 0 else None

        def do_GET(self):
            if not self._local_host():
                return self._send(403, b'forbidden', 'text/plain')
            path = unquote(self.path.split('?')[0])
            if path == '/state':
                return self._send(200, json.dumps(emu.snapshot()).encode(), TYPES['.json'])
            rel = 'index.html' if path == '/' else path.lstrip('/')
            full = os.path.normpath(os.path.join(HERE, rel))
            if not full.startswith(HERE + os.sep) or not os.path.isfile(full):   # HERE + sep: not a sibling 'ui2'
                return self._send(404, b'not found', 'text/plain')
            with open(full, 'rb') as f:
                self._send(200, f.read(), TYPES.get(os.path.splitext(full)[1], 'application/octet-stream'))

        def do_POST(self):
            if not (self._local_host() and self._same_origin()):
                return self._send(403, b'{"error":"request from another origin"}', TYPES['.json'])
            if self.path == '/quit':
                if self.headers.get('X-121GW') != 'quit':
                    return self._send(400, b'{"error":"missing header X-121GW: quit"}', TYPES['.json'])
                self._send(200, b'{"ok":true}', TYPES['.json'])
                threading.Timer(0.2, os._exit, (0,)).start()
                return
            if self.path == '/firmware':
                if self.headers.get('X-121GW') != 'firmware':
                    return self._send(400, b'{"error":"missing header X-121GW: firmware"}', TYPES['.json'])
                n = self._length()
                if n is None:
                    return self._send(400, b'{"error":"bad Content-Length"}', TYPES['.json'])
                if n > 1 << 20:
                    return self._send(413, json.dumps({'error': f'the file has {n} bytes; a firmware image has at '
                                                       f'most 368 KiB'}).encode(), TYPES['.json'])
                try:
                    emu.load_app(self.rfile.read(n), unquote(self.headers.get('X-121GW-File', '')))
                    return self._send(200, b'{"ok":true}', TYPES['.json'])
                except ValueError as e:
                    return self._send(400, json.dumps({'error': str(e)}).encode(), TYPES['.json'])
            if self.path != '/input':
                return self._send(404, b'not found', 'text/plain')
            n = self._length()
            if n is None or n > 1 << 16:
                return self._send(400, b'{"error":"bad Content-Length"}', TYPES['.json'])
            try:
                cmd = json.loads(self.rfile.read(n) or b'{}')
                emu.command(cmd)
                self._send(200, b'{"ok":true}', TYPES['.json'])
            except Exception as e:                       # report bad commands to the page
                self._send(400, json.dumps({'error': str(e)}).encode(), TYPES['.json'])
    return H


def serve(emu, port=8121, host=None):
    """host (fork, opt-in): also accept requests for this address of the computer (e.g. its LAN IP); the server then
    listens on all interfaces, and still answers only requests that name 127.0.0.1, localhost, [::1] or that address."""
    httpd = ThreadingHTTPServer(('0.0.0.0' if host else '127.0.0.1', port), make_handler(emu, host))
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    return httpd
