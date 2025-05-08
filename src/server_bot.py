# server_bot.py

import discord
import asyncio
import os
from dotenv import load_dotenv
from server_manager import ServerManager
from discord.commands import Option

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GUILD_ID = int(os.getenv("DISCORD_GUILD_ID"))

bot = discord.Bot()
manager = ServerManager()

GAME_CHOICES = ["valheim", "minecraft"]
DISPLAY_NAMES = {name: name.capitalize() for name in GAME_CHOICES}

@bot.event
async def on_ready():
    print(f"✅ Bot {bot.user} is online.")
    # Optional: stop all running servers
    async def on_ready():
        print(f"✅ Bot {bot.user} is online.")
        for server in manager.servers.values():
            server.cleanup_orphan_process()
            server.stop()

@bot.slash_command(guild_ids=[GUILD_ID], name="startserver", description="Start a game server.")
async def startserver(
    ctx: discord.ApplicationContext,
    game: str = Option(str, "Choose a game server", choices=[name.capitalize() for name in GAME_CHOICES])
):
    game_key = game.lower()
    server = manager.get_server(game_key)
    await ctx.defer(ephemeral=True)

    if not server:
        await ctx.respond(f"❌ Game '{game}' is not supported.", ephemeral=True)
        return

    if server.is_running():
        await ctx.respond(f"⚠️ {game} server is already running.", ephemeral=True)
        return

    await ctx.respond(f"⏳ Starting {game} server...", ephemeral=True)
    try:
        await server.start(ctx)
    except Exception as e:
        await ctx.channel.send(f"❌ Failed to start {game}: {e}")

@bot.slash_command(guild_ids=[GUILD_ID], name="stopserver", description="Stop a game server.")
async def stopserver(
    ctx: discord.ApplicationContext,
    game: str = Option(str, "Choose a game server", choices=[name.capitalize() for name in GAME_CHOICES])
):
    game_key = game.lower()
    server = manager.get_server(game_key)
    await ctx.defer(ephemeral=True)

    if not server:
        await ctx.respond(f"❌ Game '{game}' is not supported.", ephemeral=True)
        return

    if server.is_running():
        server.stop()
        await ctx.respond(f"🛑 {game} server stopped.", ephemeral=True)
    else:
        await ctx.respond(f"⚠️ {game} server is not running.", ephemeral=True)

@bot.slash_command(
    guild_ids=[GUILD_ID],
    name="status",
    description="Show the status of game servers."
)
async def status(
    ctx: discord.ApplicationContext,
    server: str = Option(str, description="Choose a server or 'all'", choices=[*GAME_CHOICES, "all"])
):
    lines = []

    if server == "all":
        targets = manager.servers.items()
    else:
        targets = [(server, manager.servers.get(server))]
        if targets[0][1] is None:
            await ctx.respond(f"❌ Unknown server: `{server}`", ephemeral=True)
            return

    for name, server in targets:
        if server.is_running():
            lines.append(
                f"🟢 **{name.capitalize()}**\n"
                f"👥 Players: `{server.player_count}`\n"
                f"⏱️ Uptime: `{server.get_uptime()}`"
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
    if game_key not in manager.servers:
        await ctx.respond(f"❌ Unknown game: `{game}`", ephemeral=True)
        return

    if game_key == "valheim":
        await ctx.respond("🪓 Valheim: Co-op Viking survival. Make sure Steam is running.")
    elif game_key == "minecraft":
        await ctx.respond("⛏️ Minecraft: Java Edition Use ZeroTier to connect.")

    else:
        await ctx.respond(f"ℹ️ No additional info available for `{game}`.")

def run_bot():
    bot.run(TOKEN)
