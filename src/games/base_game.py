import os
import subprocess
import asyncio
import signal
import time
import datetime
import psutil

from abc import ABC, abstractmethod


class BaseGameServer(ABC):
    def __init__(self, name: str):
        self._name = name.lower()
        self._instances = self._load_instances()
        self._active_instance = None
        self._process = None
        self._log_file = None
        self._log_file_path = None
        self._start_time = None
        self._player_count = 0
        self._timer_task = None
        self._timer_duration = 60

        self._project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        self._pid_dir = os.path.join(self._project_root, "pids")
        os.makedirs(self._pid_dir, exist_ok=True)

    @property
    def name(self) -> str:
        return self._name

    @property
    def instances(self) -> dict:
        return self._instances

    @property
    def active_instance(self) -> str:
        return self._active_instance

    @property
    def process(self):
        return self._process

    @property
    def log_file_path(self) -> str:
        return self._log_file_path

    @property
    def player_count(self) -> int:
        return self._player_count

    @player_count.setter
    def player_count(self, value: int):
        self._player_count = max(0, value)

    @property
    def is_running(self) -> bool:
        return self._process and self._process.poll() is None

    @property
    def timer_duration(self) -> int:
        return self._timer_duration

    @timer_duration.setter
    def timer_duration(self, value: int):
        self._timer_duration = value

    def _load_instances(self) -> dict:
        if not hasattr(self.__class__, "Instances"):
            raise NotImplementedError(f"{self.__class__.__name__} must define a class-level Instances dict.")
        return self.__class__.Instances


    def get_instance(self, instance_name: str):
        if not hasattr(self.__class__, "Instances") or not isinstance(self.__class__.Instances, dict):
            raise NotImplementedError(f"{self.__class__.__name__} must define a class-level Instances dict.")
        return self._instances.get(instance_name)

    def _get_pid_file(self, instance_name: str) -> str:
        safe = instance_name.lower().replace(" ", "_").replace(".", "_")
        return os.path.join(self._pid_dir, f"{self._name}_{safe}.pid")

    def _create_log_file(self, instance_name: str):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        safe = instance_name.lower().replace(" ", "_")
        log_dir = os.path.join(self._project_root, "logs", self._name, safe)
        os.makedirs(log_dir, exist_ok=True)
        self._log_file_path = os.path.join(log_dir, f"{timestamp}.log")
        self._log_file = open(self._log_file_path, "w")

    def mark_started(self):
        self._start_time = time.time()

    @property
    def uptime(self) -> str:
        if not self._start_time:
            return "Not running"
        elapsed = int(time.time() - self._start_time)
        h, m = divmod(elapsed, 3600)
        m, s = divmod(m, 60)
        return f"{h:02}:{m:02}:{s:02}"

    async def start_instance(self, instance_name: str, ctx):
        instance = self.get_instance(instance_name)
        if not instance:
            await ctx.channel.send(f"❌ No instance named {instance_name}.")
            return

        script_path = instance["script_path"]
        self._active_instance = instance_name
        self._player_count = 0
        self._create_log_file(instance_name)

        try:
            launch_args = self.get_launch_args(instance)
            self._process = subprocess.Popen(
                ["/bin/bash", *launch_args],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                preexec_fn=os.setsid,
                cwd=os.path.dirname(launch_args[0]),
            )
            self._save_pid(self._get_pid_file(instance_name))
            self.mark_started()
            asyncio.create_task(self._log_output(ctx))
        except Exception as e:
            await ctx.channel.send(f"❌ Failed to start {instance_name}: {e}")

    def stop_instance(self, instance_name: str):
        pid_file = self._get_pid_file(instance_name)
        info = self._load_pid_info(pid_file)
        if not info or not info.get("pid"):
            return

        try:
            pid = int(info["pid"])
            parent = psutil.Process(pid)
            for child in parent.children(recursive=True):
                child.terminate()
            parent.terminate()
            _, alive = psutil.wait_procs([parent] + parent.children(), timeout=5)
            for p in alive:
                p.kill()
        except Exception as e:
            print(f"[{self._name}] ❌ Error stopping instance {instance_name}: {e}")

        self._cancel_shutdown_timer()
        self._remove_pid(pid_file)
        self._process = None
        self._active_instance = None

    def cleanup_orphan_process(self):
        """
        If a PID file exists and the process is still running from a previous session, kill it.
        This is useful to avoid port conflicts or zombie servers.
        """
        for instance_name in self.instances:
            pid_file = self._get_pid_file(instance_name)
            info = self._load_pid_info(pid_file)
            if not info or "pid" not in info:
                continue

            try:
                pid = int(info["pid"])
                proc = psutil.Process(pid)
                if proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE:
                    print(f"[{self.name}:{instance_name}] 🛑 Killing orphaned process (PID {pid})")
                    proc.terminate()
                    proc.wait(timeout=5)
            except psutil.NoSuchProcess:
                pass
            except Exception as e:
                print(f"[{self.name}:{instance_name}] ⚠️ Could not clean orphaned process: {e}")

            self._remove_pid(pid_file)


    async def _log_output(self, ctx):
        if not self._process or not self._process.stdout:
            return

        with open(self._log_file_path, "a") as log_file:
            while True and self.is_running:
                line = await asyncio.to_thread(self._process.stdout.readline)
                if not line:
                    break
                decoded = line.decode("utf-8").strip()
                log_file.write(f"{decoded}\n")
                log_file.flush()
                await self.handle_output_line(ctx, decoded)

    @abstractmethod
    async def handle_output_line(self, ctx, line: str):
        """Override this in subclasses to process game-specific output lines."""
        pass

    def _save_pid(self, path: str):
        if not self._process:
            return
        try:
            with open(path, "w") as f:
                f.write(f"pid={self._process.pid}\n")
        except Exception:
            pass

    def _load_pid_info(self, path: str):
        if not os.path.exists(path):
            return None
        with open(path) as f:
            data = dict(line.strip().split("=", 1) for line in f if "=" in line)
        return data

    def _remove_pid(self, path: str):
        if os.path.exists(path):
            os.remove(path)

    def _cancel_shutdown_timer(self):
        if self._timer_task:
            self._timer_task.cancel()
            self._timer_task = None

    async def _start_shutdown_timer(self, ctx, reason: str):
        self._cancel_shutdown_timer()
        await ctx.channel.send(f"⏳ Server will shut down in {self._timer_duration} seconds ({reason})")

        async def shutdown():
            await asyncio.sleep(self._timer_duration)
            await ctx.channel.send("🛑 Shutting down due to inactivity.")
            self.stop_instance(self._active_instance)

        self._timer_task = asyncio.create_task(shutdown())

    def get_launch_args(self, instance_config: dict) -> list:
        """
        Return the command args to launch the server process.
        Subclasses can override this to provide extra arguments.
        """
        return [instance_config["script_path"]]