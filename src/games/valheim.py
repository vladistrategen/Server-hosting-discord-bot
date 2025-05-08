import os
import subprocess
import asyncio
import signal
import secrets
import string
import re
from games.base_game import BaseGameServer

class ValheimServer(BaseGameServer):
    def __init__(self):
        self.script_path = os.getenv("VALHEIM_SCRIPT_FILE_PATH")
        self.process = None
        self.password = self._generate_password()
        super().__init__("valheim", self.script_path)

    async def start(self, ctx):
        self._create_log_file()

        self.process = subprocess.Popen(
            ["/bin/zsh", self.script_path, self.password],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            preexec_fn=os.setsid,
            cwd=os.path.dirname(self.script_path),
        )
        self.save_pid()
        self.mark_started()
        asyncio.create_task(self._monitor_output(ctx))

    async def _monitor_output(self, ctx):
        invite_code = None

        with open(self.log_file_path, "a") as log_file:
            while True:
                output = await asyncio.to_thread(self.process.stdout.readline)
                if not output:
                    break
                line = output.decode("utf-8").strip()
                log_file.write(f"[STDOUT] {line}\n")
                log_file.flush()

                if "join code" in line and not invite_code:
                    match = re.search(r'join code (\d+)', line)
                    if match:
                        invite_code = match.group(1)
                        await ctx.channel.send(
                            f"✅ **Valheim server is live!**\n🔗 **Join Code:** `{invite_code}`\n🔑 **Password:** `{self.password}`"
                        )
                        await self._start_shutdown_timer(ctx, "no players joining in time")

                match = re.search(r'Player joined server.*?now (\d+) player', line)
                if match and int(match.group(1)) > 0:
                    self._cancel_shutdown_timer()
                    self.player_count = int(match.group(1))

                match = re.search(r'connection lost.*?now (\d+) player', line)
                if match and int(match.group(1)) == 0:
                    self.player_count = 0
                    await self._start_shutdown_timer(ctx, "all players disconnected")

    def _generate_password(self, length=10):
        return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(length))
