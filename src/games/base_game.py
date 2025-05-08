import asyncio
import os
import subprocess
import datetime
import signal
import time

import psutil

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

class BaseGameServer:
    def __init__(self, name: str, script_path: str):
        self.name = name
        self.script_path = script_path
        self.process = None
        self.log_file = None
        self.start_time = None
        self.player_count = 0
        self.timer_duration = 60
        self.timer_task = None
        self.pid_dir = os.path.join(PROJECT_ROOT, "pids")

        # PID setup
        self.pid_dir = os.path.join(PROJECT_ROOT, "pids")
        os.makedirs(self.pid_dir, exist_ok=True)
        self.pid_file = os.path.join(self.pid_dir, f"{self.name.lower()}.pid")

    def mark_started(self):
        self.start_time = time.time()
    
    def get_uptime(self):
        if self.start_time:
            elapsed = int(time.time() - self.start_time)
            mins, secs = divmod(elapsed, 60)
            hours, mins = divmod(mins, 60)
            return f"{hours:02d}:{mins:02d}:{secs:02d}"
        return "Not running"

    def is_running(self):
        return self.process and self.process.poll() is None

    def _create_log_file(self):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_dir = os.path.join(PROJECT_ROOT, "logs", self.name.lower())
        os.makedirs(log_dir, exist_ok=True)
        self.log_file_path = os.path.join(log_dir, f"{timestamp}.log")
        self.log_file = open(self.log_file_path, "w")


    def start(self):
        if self.process:
            raise RuntimeError("Server is already running.")

        self._create_log_file()

        self.process = subprocess.Popen(
            ["/bin/zsh", self.script_path],
            stdout=self.log_file,
            stderr=subprocess.STDOUT,
            preexec_fn=os.setsid,
            cwd=os.path.dirname(self.script_path),
        )

        self.save_pid()
        self.mark_started()

        timeout = 60
        interval = 1
        start_check_time = time.time()

        while time.time() - start_check_time < timeout:
            if self.process.poll() is not None:
                print(f"[{self.name}] ❌ Server process exited unexpectedly.")
                self.stop()
                raise RuntimeError(f"{self.name} server failed to start.")

            if os.path.exists(self.log_file_path):
                with open(self.log_file_path, "r") as log_check:
                    lines = log_check.read()
                    if any(x in lines for x in ["Done", "Server started", "Listening on"]):
                        print(f"[{self.name}] ✅ Detected successful startup.")
                        return self.process.pid

            time.sleep(interval)

        print(f"[{self.name}] ⏱️ Timeout: server did not start within {timeout} seconds.")
        self.stop()
        raise TimeoutError(f"{self.name} server did not start within timeout.")


    def stop(self):
        info = self.load_pid_info()
        if not info or not info.get("pid"):
            print(f"[{self.name}] ⚠️ No valid PID found to stop.")
            return

        pid = info["pid"]

        try:
            parent = psutil.Process(pid)
            children = parent.children(recursive=True)

            print(f"[{self.name}] 🔥 Killing process tree: {pid} + {[child.pid for child in children]}")

            for child in children:
                child.terminate()
            parent.terminate()

            _, alive = psutil.wait_procs(children + [parent], timeout=5)
            for p in alive:
                print(f"[{self.name}] ⚠️ Force killing PID {p.pid}")
                p.kill()

        except psutil.NoSuchProcess:
            print(f"[{self.name}] ⚠️ Process {pid} does not exist.")
        except Exception as e:
            print(f"[{self.name}] ❌ Error while stopping process {pid}: {e}")

        self._cancel_shutdown_timer()
        self.remove_pid()
        self.process = None

    def is_running(self):
        return self.process and self.process.poll() is None
    
    def save_pid(self):
        pid = self.process.pid
        try:
            proc = psutil.Process(pid)
            name = proc.name()
            started_at = int(proc.create_time())

            with open(self.pid_file, "w") as f:
                f.write(f"pid={pid}\n")
                f.write(f"name={name}\n")
                f.write(f"started_at={started_at}\n")

        except psutil.NoSuchProcess:
            print(f"[{self.name}] ❌ Failed to retrieve process info for PID {pid}")

    def load_pid_info(self):
        if not os.path.exists(self.pid_file):
            return None

        with open(self.pid_file, "r") as f:
            info = {}
            for line in f:
                if "=" in line:
                    key, val = line.strip().split("=", 1)
                    info[key] = val

        try:
            pid = int(info["pid"])
            proc = psutil.Process(pid)
            return {
                "pid": pid,
                "name": proc.name(),
                "started_at": int(proc.create_time()),
                "running": proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE,
            }
        except (psutil.NoSuchProcess, KeyError, ValueError):
            return None

    def cleanup_orphan_process(self):
        info = self.load_pid_info()
        if not info:
            return

        pid = info["pid"]
        name = info.get("name", "unknown")
        started_at = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(info["started_at"]))

        if info["running"]:
            print(f"[{self.name}] 🛑 Killing orphaned process (PID {pid}, {name}, started at {started_at})")
            try:
                os.killpg(pid, signal.SIGTERM)
                time.sleep(2)
            except Exception as e:
                print(f"[{self.name}] ❌ Failed to terminate: {e}")
        else:
            print(f"[{self.name}] ℹ️ Orphaned PID {pid} already not running.")

        self.remove_pid()


    def get_saved_pid(self):
        if os.path.exists(self.pid_file):
            with open(self.pid_file, "r") as f:
                pid = f.readline().strip()
                return int(pid) if pid.isdigit() else None
        return None

    def remove_pid(self):
        if os.path.exists(self.pid_file):
            os.remove(self.pid_file)

    def _cancel_shutdown_timer(self):
        if hasattr(self, 'timer_task') and self.timer_task:
            self.timer_task.cancel()
            self.timer_task = None

    async def _start_shutdown_timer(self, ctx, reason: str):
        self._cancel_shutdown_timer()
        await ctx.channel.send(f"⏳ Server will shut down in {self.timer_duration} seconds due to: {reason}")

        async def shutdown():
            await asyncio.sleep(self.timer_duration)
            await ctx.channel.send("🛑 Server shutting down due to inactivity.")
            self.stop()

        self.timer_task = asyncio.create_task(shutdown())

