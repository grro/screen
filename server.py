import logging
import sys
from time import sleep

from screen import Screen
from screen_web import ScreenWebServer
from screen_mcp import ScreenMCPServer





def run_server(port: int, name: str):
    screen = Screen()
    web_server = ScreenWebServer(screen=screen, port=port)
    mcp_server = ScreenMCPServer(screen=screen, name=name, port=port+1)
    try:
        web_server.start()
        mcp_server.start()
        sleep(666666666)
    except KeyboardInterrupt:
        logging.info('stopping the server')
        web_server.stop()
        mcp_server.stop()
        logging.info('done')


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s %(name)-20s: %(levelname)-8s %(message)s', level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S')
    logging.getLogger('tornado.access').setLevel(logging.ERROR)
    logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)
    run_server(int(sys.argv[1]), sys.argv[2])
