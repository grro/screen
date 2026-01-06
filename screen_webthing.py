import sys
import logging
import tornado.ioloop
from time import sleep
from webthing import (SingleThing, Property, Thing, Value, WebThingServer)
from screen import Screen
from screen_web import ScreenWebServer
from screen_mcp import ScreenMCPServer


class ScreenThing(Thing):

    # regarding capabilities refer https://iot.mozilla.org/schemas
    # there is also another schema registry http://iotschema.org/docs/full.html not used by webthing

    def __init__(self, name: str, screen: Screen):
        Thing.__init__(
            self,
            'urn:dev:ops:screen-1',
            'screen' + name,
            ['MultiLevelSensor'],
            "screeen"
        )
        self.ioloop = tornado.ioloop.IOLoop.current()
        self.screen = screen
        self.screen.add_listener(self.on_value_changed)

        self.on = Value(screen.on, screen.set_screen_power)
        self.add_property(
            Property(self,
                     'on',
                     self.on,
                     metadata={
                         'title': 'on',
                         "type": "boolean",
                         'description': 'True, if screen is on',
                         'readOnly': False,
                     }))


    def on_value_changed(self):
        self.ioloop.add_callback(self._on_value_changed)

    def _on_value_changed(self):
        self.on.notify_of_external_update(self.screen.on)


def run_server(port: int, name: str):
    screen = Screen()
    server = WebThingServer(SingleThing(ScreenThing(name, screen)), port=port, disable_host_validation=True)
    web_server = ScreenWebServer(screen=screen, port=port+1)
    mcp_server = ScreenMCPServer(screen=screen, name=name, port=port+2)
    try:
        web_server.start()
        mcp_server.start()
        logging.info('starting the server http://localhost:' + str(port))
        server.start()
        sleep(10000)
    except KeyboardInterrupt:
        logging.info('stopping the server')
        web_server.stop()
        mcp_server.stop()
        server.stop()
        logging.info('done')


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s %(name)-20s: %(levelname)-8s %(message)s', level=logging.INFO, datefmt='%Y-%m-%d %H:%M:%S')
    logging.getLogger('tornado.access').setLevel(logging.ERROR)
    logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)
    run_server(int(sys.argv[1]), sys.argv[2])


# test curl
# curl -X PUT -d '{"position": 40}' http://localhost:9955/0/properties/position