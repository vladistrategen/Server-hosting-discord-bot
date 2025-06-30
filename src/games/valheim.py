import os
import re
import secrets
import string
from games.base_game import BaseGameServer


class ValheimServer(BaseGameServer):
    Instances = {
        "Pantelimon": {
            "script_path": os.getenv("VALHEIM_SCRIPT_FILE_PATH")
        }
    }

    def __init__(self):
        super().__init__("valheim")
        self._invite_code = None
        self._password = self._generate_password()

    @property
    def password(self) -> str:
        return self._password

    async def handle_output_line(self, ctx, line: str):
        # detect join code (sent once)
        if "join code" in line and not self._invite_code:
            match = re.search(r'join code (\d+)', line)
            if match:
                self._invite_code = match.group(1)
                await ctx.channel.send(
                    f"✅ **Valheim `{self.active_instance}` is live!**\n"
                    f"🔗 **Join Code:** `{self._invite_code}`\n"
                    f"🔑 **Password:** `{self._password}`"
                )
                await self._start_shutdown_timer(ctx, "no players joining in time")

        #detect player join
        match = re.search(r'Player joined server.*?now (\d+) player', line)
        if match:
            count = int(match.group(1))
            if count > 0:
                self._cancel_shutdown_timer()
                self.player_count = count

        #detect player disconnect
        match = re.search(r'connection lost.*?now (\d+) player', line)
        if match:
            count = int(match.group(1))
            self.player_count = count
            if count == 0:
                await self._start_shutdown_timer(ctx, "all players disconnected")

    def get_launch_args(self, instance_config: dict) -> list:
        """Override if your server requires extra args like password."""
        return [instance_config["script_path"], self._password]

    def _generate_password(self, length=10) -> str:
        return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(length))

    def get_launch_args(self, instance_config: dict) -> list:
        return [instance_config["script_path"], self._password]