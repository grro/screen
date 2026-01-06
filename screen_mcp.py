from mcp_server import MCPServer
from screen import Screen



class ScreenMCPServer(MCPServer):

    def __init__(self, screen: Screen, name: str, port: int):
        super().__init__(name, port)
        self.screen = screen

        @self.mcp.tool()
        def get_screen_power() -> str:
            """
            Retrieves the current power status of the screen.

            Returns:
                str: A message stating whether the screen is currently on or off.
            """
            try:
                state_str = "on" if self.screen.on else "off"
                return f"The screen is currently {state_str}."
            except Exception as e:
                return f"Error retrieving screen state: {str(e)}"


        @self.mcp.tool()
        def set_screen_power(on: bool) -> str:
            """
            Controls the power state of the screen.

            Args:
                on (bool): Set to True to turn the screen on, False to turn it off.

            Returns:
                str: A confirmation message indicating the new state of the screen.
            """
            try:
                # Using self.screen to ensure we reference the instance variable
                self.screen.set_screen_power(on)
                state_str = "on" if on else "off"
                return f"Screen successfully turned {state_str}."
            except Exception as e:
                return f"Failed to change screen power state: {str(e)}"



# npx @modelcontextprotocol/inspector

