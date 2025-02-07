import re
import time
import discord
import os
import signal
import secrets
import string
import subprocess
import asyncio
from dotenv import load_dotenv
import psutil

load_dotenv()

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
SCRIPT_FILE_PATH = os.getenv("SCRIPT_FILE_PATH")  # Path to custom_start_server.sh
PID_FILE = "valheim_server.pid"
LOG_FILE_PATH = "subproc.log"
GUILD_ID = os.getenv("DISCORD_GUILD_ID")
TIMER_DURATION = 90  # Time before shutting down if no players join

if not SCRIPT_FILE_PATH:
    raise ValueError("SCRIPT_FILE_PATH environment variable is not set.")

bot = discord.Bot()
server_process = None 


def generate_random_password(length=10):
    """Generate a random alphanumeric password."""
    characters = string.ascii_letters + string.digits
    return ''.join(secrets.choice(characters) for _ in range(length))


def save_pid(pid):
    """Save the current server process PID to a file."""
    with open(PID_FILE, "w") as f:
        f.write(f"{pid}\n")


def get_saved_pid():
    """Retrieve the saved PID."""
    if os.path.exists(PID_FILE):
        with open(PID_FILE, "r") as f:
            pid = f.readline().strip()
            return int(pid) if pid.isdigit() else None
    return None


def remove_pid():
    """Remove the stored PID file."""
    if os.path.exists(PID_FILE):
        os.remove(PID_FILE)


def stop_server():
    """Stop the running Valheim server."""
    global server_process
    pid = get_saved_pid()
    if pid:
        try:
            print(f"🔴 Stopping Valheim server (PID {pid})...")
            os.killpg(pid, signal.SIGTERM) 
            time.sleep(10)  # Wait for clean exit

            # If still running, use pkill to force terminate all related processes
            # if psutil.pid_exists(pid):
            #     print(f"⚠️ Server did not exit, force-killing process {pid}.")
            #     subprocess.run(["sudo","pkill", "-9", "-P", str(pid)], check=False)

            remove_pid()
            server_process = None
            return True

        except ProcessLookupError:
            print(f"⚠️ Process {pid} not running.")
            remove_pid()
        except Exception as e:
            print(f"❌ Error stopping process {pid}: {e}")
    return 


@bot.slash_command(guild_ids=[int(GUILD_ID)], name="startserver", description="Start a specific game server.")
async def startserver(ctx: discord.ApplicationContext, game: str):
    """Starts the game server using the shell script asynchronously."""
    global server_process

    await ctx.defer(ephemeral=True)

    if game.lower() != "valheim":
        await ctx.respond("⚠️ Only **Valheim** is supported for now!", ephemeral=True)
        return

    if get_saved_pid():
        await ctx.respond("⚠️ **Server is already running!**", ephemeral=True)
        return

    password = generate_random_password()

    await ctx.respond("⏳ **Starting Valheim server...**", ephemeral=True)

    try:
        server_process = subprocess.Popen(
            ["/bin/zsh", SCRIPT_FILE_PATH, password],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            preexec_fn=os.setsid,
            cwd=os.path.dirname(SCRIPT_FILE_PATH),
        )

        save_pid(server_process.pid)

        asyncio.create_task(monitor_output(ctx, server_process, password))

    except Exception as e:
        await ctx.channel.send(f"❌ **Failed to start server:** {e}")

async def monitor_output(ctx, process, password):
    """Monitors both stdout and stderr asynchronously, extracts join code, and logs output."""
    invite_code = None

    with open(LOG_FILE_PATH, "w") as log_file:
        while True:
            output = await asyncio.to_thread(process.stdout.readline)
            if not output:
                break

            decoded_line = output.decode("utf-8").strip()
            log_file.write(f"[STDOUT] {decoded_line}\n")
            log_file.flush()

            if "join code" in decoded_line and not invite_code:
                match = re.search(r'join code (\d+)', decoded_line)
                if match:
                    invite_code = match.group(1)
                    await ctx.channel.send(
                        f"✅ **Server is live!**\n🔗 **Join Code:** `{invite_code}`\n🔑 **Password:** `{password}`"
                    )

            if "PlayFab create lobby failed" in decoded_line:
                raise Exception("Too many servers running.")
            if "NullReferenceException: The WorldGenerator instance was null" in decoded_line:
                raise Exception("Nu merge steamu, MA OMOR - Vlad")
       

# async def monitor_output(ctx, process, password):
#     """Monitors server output, extracts join code, and manages shutdown timers."""
#     try:
#         invite_code = None
#         active_timer = None

#         def cancel_existing_timer():
#             """Cancels the active timer if it exists."""
#             nonlocal active_timer
#             if active_timer:
#                 active_timer.cancel()
#                 active_timer = None

#         async def start_shutdown_timer(reason):
#             """Starts a 90s shutdown timer if no players are connected."""
#             nonlocal active_timer
#             await ctx.channel.send(f"⏳ **Server will shut down in {TIMER_DURATION} seconds** due to: {reason}")

#             async def shutdown():
#                 await asyncio.sleep(TIMER_DURATION)
#                 await ctx.channel.send(f"🛑 **Server shutting down due to inactivity.**")
#                 stop_server()

#             active_timer = asyncio.create_task(shutdown())

#         with open(LOG_FILE_PATH, "w") as log_file:
#             while True:
#                 output = await asyncio.to_thread(process.stdout.readline)
#                 if not output:
#                     break

#                 decoded_line = output.decode("utf-8").strip()
#                 log_file.write(f"[STDOUT] {decoded_line}\n")
#                 log_file.flush()

#                 # Extract Join Code
#                 if "join code" in decoded_line and not invite_code:
#                     match = re.search(r'join code (\d+)', decoded_line)
#                     if match:
#                         invite_code = match.group(1)
#                         await ctx.channel.send(
#                             f"✅ **Server is live!**\n🔗 **Join Code:** `{invite_code}`\n🔑 **Password:** `{password}`"
#                         )
#                         await start_shutdown_timer("no players joining in time")

#                 # Detect Player Join Event
#                 match = re.search(r'Player joined server ".*?" that has join code (\d+), now (\d+) player\(s\)', decoded_line)
#                 if match:
#                     player_count = int(match.group(2))
#                     if player_count > 0:
#                         cancel_existing_timer()
#                         await ctx.channel.send(f"🎮 **A player has joined! Active players: {player_count}**")

#                 # Detect Player Disconnect Event
#                 match = re.search(r'Player connection lost server ".*?" that has join code (\d+), now (\d+) player\(s\)', decoded_line)
#                 if match:
#                     player_count = int(match.group(2))
#                     if player_count == 0:
#                         await start_shutdown_timer("all players disconnected")

#                 # Error Handling for Steam Issues
#                 if "PlayFab create lobby failed" in decoded_line:
#                     raise Exception("Too many servers running.")
#                 if "NullReferenceException: The WorldGenerator instance was null" in decoded_line:
#                     raise Exception("Nu merge steamu, MA OMOR - Vlad")
#     except Exception as e:
#         await ctx.channel.send(f"❌ **Failed to start server:** {e}")



@bot.slash_command(guild_ids=[int(GUILD_ID)], name="stopserver", description="Stop the running game server.")
async def stopserver(ctx: discord.ApplicationContext):
    """Stops the currently running game server."""
    await ctx.defer(ephemeral=True)

    if stop_server():
        await ctx.followup.send("✅ **Server stopped successfully.**")
    else:
        await ctx.followup.send("⚠️ **No server was running.**")
    await ctx.send("🛑 **Server stopped successfully.**")


@bot.event
async def on_ready():
    print(f"{bot.user} is ready and online!")
    stop_server()


async def shutdown():
    """Handles cleanup before bot shutdown."""
    print("Stopping Valheim server before shutting down...")
    stop_server()
    await bot.close()


def signal_handler(signum, frame):
    """Handles termination signals."""
    print(f"Received signal {signum}. Shutting down...")
    asyncio.create_task(shutdown())


if __name__ == "__main__":
    stop_server()  # Stop any lingering processes before bot starts
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        bot.run(TOKEN)
    except KeyboardInterrupt:
        print("KeyboardInterrupt received. Exiting.")
        stop_server()
