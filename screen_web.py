import json
import threading
import logging
from urllib.parse import urlparse, parse_qs
from http.server import HTTPServer, BaseHTTPRequestHandler
from screen import Screen
from typing import Dict, Any


class SimpleRequestHandler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        # suppress access logging
        pass

    def do_GET(self):
        screen: Screen = self.server.screen
        parsed_url = urlparse(self.path)
        query_params = parse_qs(parsed_url.query)
        if 'on' in query_params:
            val = query_params['on'][0].lower()
            on_state = val in ['true', '1', 'on']
            try:
                if on_state:
                    screen.activate_screen(force=True)
                else:
                    screen.deactivate_screen()
                self._send_json(200, {"status": "success", "screen_on": screen.is_screen_on})
            except Exception as e:
                self._send_json(500, {"error": str(e)})
        else:
            self._send_json(200, {"screen_on": screen.is_screen_on})

    def _send_json(self, status, data: Dict[str, Any]):
        self.send_response(status)
        self.send_header("Content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

class ScreenWebServer:
    def __init__(self, screen: Screen,  host='0000', port=8000):
        self.host = host
        self.port = port
        self.address = (self.host, self.port)
        self.server = HTTPServer(self.address, SimpleRequestHandler)
        self.server.screen = screen
        self.server_thread = None

    def start(self):
        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.daemon = True
        self.server_thread.start()
        logging.info(f"web server started http://{self.host}:{self.port}")

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        logging.info("web server stopped")

