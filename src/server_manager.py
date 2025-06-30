# server_manager.py

from games.minecraft import MinecraftServer
from games.valheim import ValheimServer

class ServerManager:
    def __init__(self):
        self.servers = {
            "minecraft": MinecraftServer(),
            "valheim": ValheimServer(),
        }

    def get_server(self, name: str):
        return self.servers.get(name.lower())
    
    def is_any_server_running(self) -> bool:
        """Check if any server is currently running."""
        return any(server.is_running for server in self.servers.values())
