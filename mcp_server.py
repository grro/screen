import asyncio
from mcp.server.fastmcp import FastMCP
from threading import Thread
import logging




class MCPServer:

    def __init__(self, name: str, port: int):
        self.port = port
        self.mcp = FastMCP(name, host='0.0.0.0', port=self.port)
        self.new_loop = asyncio.new_event_loop()

    async def __run_async(self):
        await self.mcp.run_sse_async()

    def __start_loop(self, loop):
        asyncio.set_event_loop(loop)
        loop.run_forever()

    def start(self):
        t = Thread(target=self.__start_loop, args=(self.new_loop,), daemon=True)
        t.start()
        asyncio.run_coroutine_threadsafe(self.__run_async(), self.new_loop)
        logging.info("MCP Server running on http://localhost:" + str(self.port) + "/sse")

    def stop(self):
        self.new_loop.stop()
        logging.info("MCP Server stopped")

# claude mcp add --transport sse energyTest http://192.168.1.99:9843/sse


