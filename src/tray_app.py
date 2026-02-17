from __future__ import annotations

import logging
import os
import subprocess
import threading
from pathlib import Path

import pystray
from PIL import Image, ImageDraw
from pystray import MenuItem as item


LOGGER = logging.getLogger("discord_codex_tray")
ICON_FILE_RELATIVE_PATH = Path("assets") / "codex-gateway-icon-final.png"


def _configure_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "tray.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[logging.FileHandler(log_path, encoding="utf-8")],
    )


def _create_icon_image() -> Image.Image:
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((6, 6, 58, 58), fill=(23, 162, 184, 255))
    draw.rectangle((20, 20, 44, 42), fill=(255, 255, 255, 255))
    draw.rectangle((24, 26, 28, 30), fill=(23, 162, 184, 255))
    draw.rectangle((36, 26, 40, 30), fill=(23, 162, 184, 255))
    draw.rectangle((24, 34, 40, 36), fill=(23, 162, 184, 255))
    return image


def _load_icon_image(project_root: Path) -> Image.Image:
    icon_path = project_root / ICON_FILE_RELATIVE_PATH
    if icon_path.exists():
        try:
            return Image.open(icon_path).convert("RGBA")
        except Exception:
            LOGGER.exception("Failed to load tray icon at %s. Using fallback icon.", icon_path)
    return _create_icon_image()


class BotSupervisor:
    def __init__(self, project_root: Path, python_exe: Path) -> None:
        self._project_root = project_root
        self._python_exe = python_exe
        self._lock = threading.Lock()
        self._process: subprocess.Popen[str] | None = None

    def _spawn(self) -> None:
        flags = 0
        if os.name == "nt":
            flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.CREATE_NO_WINDOW

        self._process = subprocess.Popen(
            [str(self._python_exe), "-m", "src.bot"],
            cwd=str(self._project_root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            creationflags=flags,
        )
        LOGGER.info("Started bot process pid=%s", self._process.pid)

    def ensure_running(self) -> None:
        with self._lock:
            if self._process is None:
                self._spawn()
                return

            return_code = self._process.poll()
            if return_code is not None:
                LOGGER.warning("Bot process exited with code=%s. Restarting.", return_code)
                self._spawn()

    def restart(self) -> None:
        self.stop()
        self.ensure_running()

    def stop(self) -> None:
        with self._lock:
            if self._process is None:
                return
            if self._process.poll() is not None:
                self._process = None
                return

            pid = self._process.pid
            self._process.terminate()
            try:
                self._process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                LOGGER.warning("Force killing bot process pid=%s", pid)
                self._process.kill()
                self._process.wait(timeout=3)

            LOGGER.info("Stopped bot process pid=%s", pid)
            self._process = None

    def status(self) -> str:
        with self._lock:
            if self._process is None:
                return "parado"
            code = self._process.poll()
            if code is None:
                return f"rodando (pid {self._process.pid})"
            return f"parado (exit {code})"


def _open_path(path: Path) -> None:
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    log_dir = project_root / "logs"
    _configure_logging(log_dir)

    venv_python = project_root / ".venv" / "Scripts" / "python.exe"
    python_exe = venv_python if venv_python.exists() else Path("python.exe")
    supervisor = BotSupervisor(project_root=project_root, python_exe=python_exe)
    supervisor.ensure_running()

    stop_event = threading.Event()

    def watchdog() -> None:
        while not stop_event.is_set():
            try:
                supervisor.ensure_running()
            except Exception:
                LOGGER.exception("Unexpected error in watchdog loop")
            stop_event.wait(5)

    watcher = threading.Thread(target=watchdog, daemon=True, name="bot-watchdog")
    watcher.start()

    def on_restart(icon: pystray.Icon, _menu_item: pystray.MenuItem) -> None:
        supervisor.restart()
        icon.notify("Bot reiniciado.")

    def on_open_logs(_icon: pystray.Icon, _menu_item: pystray.MenuItem) -> None:
        _open_path(log_dir)

    def on_open_project(_icon: pystray.Icon, _menu_item: pystray.MenuItem) -> None:
        _open_path(project_root)

    def on_exit(icon: pystray.Icon, _menu_item: pystray.MenuItem) -> None:
        stop_event.set()
        supervisor.stop()
        icon.stop()

    icon = pystray.Icon(
        "CodexDiscordGateway",
        _load_icon_image(project_root),
        "Codex Discord Gateway",
        menu=pystray.Menu(
            item(
                lambda _item: f"Status: {supervisor.status()}",
                lambda _icon, _menu_item: None,
                enabled=False,
            ),
            item("Reiniciar bot", on_restart),
            item("Abrir logs", on_open_logs),
            item("Abrir pasta do projeto", on_open_project),
            item("Sair", on_exit),
        ),
    )

    LOGGER.info("Tray app started")
    icon.run()
    LOGGER.info("Tray app stopped")


if __name__ == "__main__":
    main()
