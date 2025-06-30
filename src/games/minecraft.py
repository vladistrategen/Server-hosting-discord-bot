import os
import socket
import re
from games.base_game import BaseGameServer


class MinecraftServer(BaseGameServer):
    Instances = {
        "Modded 1.21.1 NeoForge BMC5": {
            "script_path": os.getenv("MINECRAFT_MODDED_1_21_1_NEOFORGE_BMC5_SCRIPT_FILE_PATH")
        },
        "Vanilla Fabric 1.21.5": {
            "script_path": os.getenv("MINECRAFT_VANILLA_FABRIC_1_21_5_SCRIPT_FILE_PATH")
        },
    }

    def __init__(self):
        super().__init__("minecraft")

    async def handle_output_line(self, ctx, line: str):
        if "Done" in line:
            ip = self._get_local_ip()
            await ctx.channel.send(
                f"✅ **Minecraft `{self.active_instance}` is live!**\n🌐 IP: `{ip}:25565` using ZeroTier"
            )
            await self._start_shutdown_timer(ctx, reason="no players joined")

        elif "joined the game" in line:
            self._cancel_shutdown_timer()
            self.player_count += 1
            await ctx.channel.send("🎮 A player joined. Shutdown cancelled.")

        elif "left the game" in line:
            self.player_count -= 1
            if self.player_count == 0:
                await ctx.channel.send("👤 All players left. Starting shutdown timer.")
                await self._start_shutdown_timer(ctx, reason="all players left")

        elif "Shutting down" in line:
            if "[main/ERROR]" in line:
                await ctx.channel.send("❌ Server crashed.")
            else:
                await ctx.channel.send("🛑 Minecraft server is shutting down.")
            self._process = None

    def _get_local_ip(self) -> str:
        try:
            out = os.popen("zerotier-cli listnetworks").read()
            match = re.search(r'(\d{1,3}(?:\.\d{1,3}){3})\/\d+', out)
            if match:
                return match.group(1)
        except:
            pass

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "Unknown"
