import os
import subprocess
import asyncio
import signal
import socket
import re
from games.base_game import BaseGameServer

class MinecraftServer(BaseGameServer):
    def __init__(self):
        self.script_path = os.getenv("MINECRAFT_SCRIPT_FILE_PATH")
        self.process = None
        self.timer_task = None
        self.timer_duration = 120
        super().__init__("minecraft", self.script_path)


    async def start(self, ctx):
        try:
            self._create_log_file()
            self.process = subprocess.Popen(
                ["/bin/zsh", self.script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid,
                cwd=os.path.dirname(self.script_path),
            )
            self.save_pid()
            asyncio.create_task(self._log_output(ctx))
        except Exception as e:
            await ctx.channel.send(f"❌ Failed to start Minecraft: {e}")

    async def _log_output(self, ctx):
        if not self.process or not self.process.stdout:
            print(f"[{self.name}] ❌ Cannot log output — process is not running.")
            return

        with open(self.log_file_path, "a") as log_file:
            while True:
                output = await asyncio.to_thread(self.process.stdout.readline)
                if not output:
                    break
                line = output.decode("utf-8").strip()
                log_file.write(f"[MC] {line}\n")
                log_file.flush()

                if "Done" in line:
                    ip = self._get_local_ip()
                    await ctx.channel.send(
                        f"✅ **Minecraft server is live with ZeroTier!**\n🌐 IP: `{ip}:25565`"
                    )
                    await self._start_shutdown_timer(ctx, reason="no players joined")
                
                if "Shutting down" in line:
                    self.process = None
                    if "[main/ERROR]" in line:
                        await ctx.channel.send("❌ **Minecraft server encountered an error and is shutting down.**")
                        break
                    await ctx.channel.send("🛑 **Minecraft server is shutting down.**")
                    break

                if "joined the game" in line:
                    self._cancel_shutdown_timer()
                    self.player_count += 1
                    await ctx.channel.send("🎮 A player joined. Canceling shutdown timer.")

                if "left the game" in line:
                    self.player_count -= 1
                    if self.player_count == 0:
                        await ctx.channel.send("👤 All players left. Starting shutdown timer.")
                        await self._start_shutdown_timer(ctx, reason="all players left")
                        
    def _get_local_ip(self):
        try:
            zt_output = os.popen("zerotier-cli listnetworks").read()
            for line in zt_output.splitlines():
                match = re.search(r'(\d{1,3}(?:\.\d{1,3}){3})\/\d+$', line)
                if match:
                    return match.group(1)
        except Exception:
            pass

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "Unknown"
