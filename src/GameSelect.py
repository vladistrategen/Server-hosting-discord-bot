# GameSelect.py

import discord
from discord.ui import View, Select
from discord import SelectOption, Interaction
from server_manager import ServerManager


class InstanceSelect(Select):
    def __init__(self, game: str, manager: ServerManager):
        self.manager = manager
        self.game = game
        server = self.manager.get_server(game)

        options = [SelectOption(label=inst, value=inst) for inst in server.instances]
        super().__init__(placeholder="Choose an instance...", options=options)

    async def callback(self, interaction: Interaction):
        server = self.manager.get_server(self.game)
        instance = self.values[0]
        await interaction.response.edit_message(
            content=f"⏳ Starting `{self.game}` instance `{instance}`...",
            view=None
        )
        try:
            await server.start_instance(instance, interaction)
        except Exception as e:
            await interaction.followup.send(f"❌ Failed to start `{instance}`: {e}", ephemeral=True)


class InstanceView(View):
    def __init__(self, game: str, manager: ServerManager):
        super().__init__(timeout=60)
        self.add_item(InstanceSelect(game, manager))

class StopInstanceSelect(Select):
    def __init__(self, game: str, manager: ServerManager):
        self.manager = manager
        self.game = game
        server = self.manager.get_server(game)
        options = [SelectOption(label=inst, value=inst) for inst in server.instances]
        super().__init__(placeholder="Choose an instance to stop...", options=options)

    async def callback(self, interaction: Interaction):
        server = self.manager.get_server(self.game)
        instance = self.values[0]
        if server.is_running:
            server.stop_instance(instance)
            await interaction.response.edit_message(
                content=f"🛑 `{self.game}` instance `{instance}` stopped.",
                view=None
            )
        else:
            await interaction.response.edit_message(
                content=f"⚠️ `{self.game}` is not currently running.",
                view=None
            )


class StopInstanceView(View):
    def __init__(self, game: str, manager: ServerManager):
        super().__init__(timeout=60)
        self.add_item(StopInstanceSelect(game, manager))
