import discord
import os
from dotenv import load_dotenv
from GameSelect import InstanceView
from server_manager import ServerManager
from discord.commands import Option

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GUILD_ID = int(os.getenv("DISCORD_GUILD_ID"))
ZERO_TIER_NETWORK_ID = os.getenv("ZEROTIER_NETWORK_ID")

bot = discord.Bot()
manager = ServerManager()

GAME_CHOICES = list(manager.servers.keys())
DISPLAY_NAMES = {name: name.capitalize() for name in GAME_CHOICES}
INSTANCE_CHOICES = {
    game: list(server.instances.keys())
    for game, server in manager.servers.items()
}
ALL_INSTANCE_NAMES = list({inst for inst_list in INSTANCE_CHOICES.values() for inst in inst_list})

@bot.event
async def on_ready():
    print(f"✅ Bot {bot.user} is online.")
    for server in manager.servers.values():
        server.cleanup_orphan_process()

@bot.slash_command(guild_ids=[GUILD_ID], name="startserver", description="Start a game server.")
async def startserver(
    ctx: discord.ApplicationContext,
    game: str = Option(str, "Choose a game", choices=[name.capitalize() for name in manager.servers])
):
    await ctx.defer(ephemeral=True)
    if manager.is_any_server_running():
        await ctx.respond("❌ A server is already running. Please stop it first.", ephemeral=True)
        return
    game_key = game.lower()
    server = manager.get_server(game_key)
    
    if not server:
        await ctx.respond(f"❌ Game {game} not found.", ephemeral=True)
        return

    instance_names = list(server.instances.keys())

    if len(instance_names) == 0:
        await ctx.respond(f"❌ No instances configured for {game}.", ephemeral=True)
        return

    elif len(instance_names) == 1:
        instance = instance_names[0]
        if server.is_running:
            await ctx.respond(f"⚠️ {game} instance {instance} is already running.", ephemeral=True)
            return

        await ctx.respond(f"⏳ Starting {game} instance {instance}...", ephemeral=True)
        try:
            await server.start_instance(instance, ctx)
        except Exception as e:
            await ctx.channel.send(f"❌ Failed to start {instance}: {e}")
        return

    else:
        # Multiple instances, show instance picker
        await ctx.respond(
            f"📦 {game} has multiple instances. Select one:",
            view=InstanceView(game, manager),
            ephemeral=True
        )


from GameSelect import StopInstanceView  # new View class for stopping

@bot.slash_command(guild_ids=[GUILD_ID], name="stopserver", description="Stop a game server.")
async def stopserver(
    ctx: discord.ApplicationContext,
    game: str = Option(str, "Choose a game", choices=[name.capitalize() for name in manager.servers])
):
    await ctx.defer(ephemeral=True)
    game_key = game.lower()
    server = manager.get_server(game_key)

    if not server:
        await ctx.respond(f"❌ Game {game} is not supported.", ephemeral=True)
        return

    instance_names = list(server.instances.keys())

    if len(instance_names) == 0:
        await ctx.respond(f"❌ No instances configured for {game}.", ephemeral=True)
        return

    elif len(instance_names) == 1:
        instance = instance_names[0]
        if server.is_running:
            server.stop_instance(instance)
            await ctx.respond(f"🛑 {game} instance {instance} stopped.", ephemeral=True)
        else:
            await ctx.respond(f"⚠️ {game} is not running.", ephemeral=True)
        return

    else:
        # Multiple instances, show selection view
        await ctx.respond(
            f"🛑 {game} has multiple instances. Select one to stop:",
            view=StopInstanceView(game, manager),
            ephemeral=True
        )


@bot.slash_command(guild_ids=[GUILD_ID], name="status", description="Show server status.")
async def status(
    ctx: discord.ApplicationContext,
    game: str = Option(str, "Choose a server or 'all'", choices=[*GAME_CHOICES, "all"])
):
    await ctx.defer(ephemeral=True)
    lines = []

    if game == "all":
        targets = manager.servers.items()
    else:
        game = game.lower()
        targets = [(game, manager.get_server(game))]
        if not targets[0][1]:
            await ctx.respond(f"❌ Unknown server: {game}", ephemeral=True)
            return

    for name, server in targets:
        if server.is_running:
            lines.append(
                f"🟢 **{name.capitalize()}** {server.active_instance}\n"
                f"👥 Players: {server.player_count}\n"
                f"⏱️ Uptime: {server.uptime}"
            )
        else:
            lines.append(f"🔴 **{name.capitalize()}** - not running.")

    await ctx.respond("\n\n".join(lines))


@bot.slash_command(guild_ids=[GUILD_ID], name="info", description="Show info about a game server.")
async def info(
    ctx: discord.ApplicationContext,
    game: str = Option(str, "Select a game", choices=[name.capitalize() for name in GAME_CHOICES])
):
    game_key = game.lower()
    server = manager.get_server(game_key)

    if not server:
        await ctx.respond(f"❌ Unknown game: {game}", ephemeral=True)
        return

    if game_key == "valheim":
        await ctx.respond(
            "**🪓 Valheim Server Info**\n"
            "- This is a co-op survival game set in Norse mythology.\n"
            "- A join code and random password will be provided once the server starts.\n"
            "- Launch Valheim through Steam.\n"
            "- Select 'Join Game' → press 'Join with Code' and enter the provided code and password.\n"
            "- No mods are required for joining.\n"
        )
        return

    if game_key == "minecraft":
        await ctx.respond(
            "**⛏️ Minecraft Java Server Info**\n"
            "- Make sure you have **Java Edition** installed.\n"
            "- You must be connected to **ZeroTier** VPN.\n"
            f"- Network ID: `{ZERO_TIER_NETWORK_ID}` (join from ZeroTier client).\n\n"
            "**Available Instances:**\n"
            "**🔸 Modded 1.21.1 NeoForge BMC5**\n"
            "- Modpack with ~310 mods. +- Distant Horizons\n"
            "- Make sure to install the provided modpack via CurseForge, using **Neoforge API**.\n\n"
            "**🔸 Vanilla Fabric 1.21.5**\n"
            "- Minimal mods (just QoL, like minimap and performance boosts and Distant Horizons).\n"
            "- Download and use Fabric loader for 1.21.5.\n"
            "- You can use your regular client, just ensure Fabric is installed.\n\n"
        )
        return

    await ctx.respond(f"ℹ️ No info available for `{game}`.")


def run_bot():
    bot.run(TOKEN)
