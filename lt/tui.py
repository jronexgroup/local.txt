import os
import threading
import time as time_module
from datetime import datetime

from rich.text import Text
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, Container
from textual.reactive import reactive
from textual.screen import Screen
from textual.worker import Worker, WorkerState
from textual.widgets import (
    Button, Footer, Header, Input, Label, ListItem, ListView,
    ProgressBar, RichLog, Static, Select, Checkbox,
)

from . import config
from . import protocol as p
from .engine import ChatEngine


class OnboardingScreen(Screen):
    def compose(self):
        yield Header(show_clock=True)
        with Vertical(id="onboarding"):
            yield Static("[bold cyan]Welcome to LT![/]", id="welcome")
            yield Static("Let's get you connected.", classes="hint")
            yield Static("")
            yield Static("[bold]Connection mode:[/]")
            yield Select(
                id="mode-select",
                prompt="Choose mode",
                options=[
                    ("LAN (same WiFi)", "lan"),
                    ("P2P (internet, direct)", "p2p"),
                    ("Tor (internet, private)", "tor"),
                ],
            )
            yield Static("")
            yield Static("[bold]Display name:[/]")
            yield Input(id="display-name", placeholder=config.get("display_name", ""))
            yield Static("")
            yield Button("Next", id="next-btn", variant="primary")

    def on_button_pressed(self, event):
        if event.button.id == "next-btn":
            mode = self.query_one("#mode-select").value
            dname = self.query_one("#display-name").value.strip() or config.get("display_name", "")
            config.save({"mode": mode, "display_name": dname})

            if mode == "lan":
                self.app.push_screen(LanSetupScreen())
            elif mode == "p2p":
                self.app.push_screen(PairSetupScreen("p2p"))
            elif mode == "tor":
                self.app.push_screen(PairSetupScreen("tor"))


class LanSetupScreen(Screen):
    def compose(self):
        yield Header(show_clock=True)
        with Vertical(id="lan-setup"):
            yield Static("[bold cyan]LAN Setup[/]", classes="hint")
            yield Static("[bold]Peer IP address:[/]")
            yield Input(id="peer-ip", placeholder="192.168.1.105")
            yield Static("[bold]Port:[/]")
            yield Input(id="port", placeholder="5050")
            yield Static("")
            yield Horizontal(
                Button("Back", id="back-btn"),
                Button("Save & Connect", id="save-btn", variant="primary"),
            )

    def on_button_pressed(self, event):
        if event.button.id == "back-btn":
            self.app.pop_screen()
        elif event.button.id == "save-btn":
            ip = self.query_one("#peer-ip").value.strip()
            port_str = self.query_one("#port").value.strip() or "5050"
            port = int(port_str) if port_str.isdigit() else 5050
            config.save({"peer_ip": ip, "port": port, "mode": "lan"})
            self.app.pop_screen()
            self.app.push_screen(ChatScreen())


class PairSetupScreen(Screen):
    def __init__(self, mode: str):
        super().__init__()
        self._mode = mode

    def compose(self):
        mode_name = {"p2p": "P2P (Direct)", "tor": "Tor"}[self._mode]
        yield Header(show_clock=True)
        with Vertical(id="pair-setup"):
            yield Static(f"[bold cyan]{mode_name} Setup[/]", classes="hint")
            yield Static("Create a secret pairing password.")
            yield Static("Your friend must use the [bold]same password[/].")
            yield Static("")
            yield Static("[bold]Pairing password:[/]")
            yield Input(id="password", password=True, placeholder="Enter secret password")
            yield Static("[bold]Confirm password:[/]")
            yield Input(id="password-confirm", password=True, placeholder="Re-enter password")
            if self._mode == "p2p":
                yield Static("")
                yield Static("[bold]Port (for P2P):[/]")
                yield Input(id="port", placeholder="5050")
            elif self._mode == "tor":
                yield Static("")
                yield Static("Tor must be installed and running on your system.")
            yield Static("")
            yield Horizontal(
                Button("Back", id="back-btn"),
                Button("Save & Connect", id="save-btn", variant="primary"),
            )

    def on_button_pressed(self, event):
        if event.button.id == "back-btn":
            self.app.pop_screen()
        elif event.button.id == "save-btn":
            pw = self.query_one("#password").value
            pw2 = self.query_one("#password-confirm").value
            if pw != pw2:
                self.app.notify("Passwords don't match!", severity="error")
                return
            if len(pw) < 4:
                self.app.notify("Password must be at least 4 characters", severity="error")
                return
            data = {"pair_password": pw, "mode": self._mode, "display_name": config.get("display_name", "")}
            if self._mode == "p2p":
                port_str = self.query_one("#port").value.strip() or "5050"
                data["port"] = int(port_str) if port_str.isdigit() else 5050
            config.save(data)
            self.app.pop_screen()
            self.app.push_screen(ChatScreen())


class SettingsScreen(Screen):
    def compose(self):
        cfg = config.load()
        yield Header(show_clock=True)
        with Vertical(id="settings"):
            yield Static("[bold cyan]Settings[/]", id="settings-title")

            yield Static("[bold]Display Name:[/]")
            yield Input(id="s-display-name", value=cfg.get("display_name", ""))

            yield Static("[bold]Theme:[/]")
            yield Select(id="s-theme", options=[("Dark", "dark"), ("Light", "light")], value=cfg.get("theme", "dark"))

            yield Static("[bold]Show Timestamps:[/]")
            yield Checkbox(value=cfg.get("show_timestamps", True), id="s-timestamps")

            yield Static("[bold]Auto-Reconnect:[/]")
            yield Checkbox(value=cfg.get("auto_reconnect", True), id="s-reconnect")

            yield Static("[bold]Auto-Accept Files:[/]")
            yield Checkbox(value=cfg.get("auto_accept_files", False), id="s-auto-files")

            yield Static("[bold]Download Directory:[/]")
            yield Input(id="s-download", value=cfg.get("download_dir", ""))

            yield Static("")
            yield Horizontal(
                Button("Reset", id="reset-btn"),
                Button("Cancel", id="cancel-btn"),
                Button("Save", id="save-btn", variant="primary"),
            )

    def on_button_pressed(self, event):
        if event.button.id == "save-btn":
            config.save({
                "display_name": self.query_one("#s-display-name").value.strip(),
                "theme": self.query_one("#s-theme").value,
                "show_timestamps": self.query_one("#s-timestamps").value,
                "auto_reconnect": self.query_one("#s-reconnect").value,
                "auto_accept_files": self.query_one("#s-auto-files").value,
                "download_dir": self.query_one("#s-download").value.strip(),
            })
            self.app.notify("Settings saved!", severity="information")
            self.app.pop_screen()
        elif event.button.id == "cancel-btn":
            self.app.pop_screen()
        elif event.button.id == "reset-btn":
            cfg = config.load()
            self.query_one("#s-display-name").value = ""
            self.query_one("#s-theme").value = "dark"
            self.query_one("#s-timestamps").value = True
            self.query_one("#s-reconnect").value = True
            self.query_one("#s-auto-files").value = False
            self.query_one("#s-download").value = os.path.expanduser("~/Downloads/LT")
            self.app.notify("Reset to defaults (not saved yet)", severity="information")


class ConnectCodeScreen(Screen):
    def __init__(self, engine: ChatEngine):
        super().__init__()
        self.engine = engine

    def compose(self):
        yield Header(show_clock=True)
        with Vertical(id="connect-code"):
            yield Static("[bold cyan]Share this with your friend[/]")
            yield Static("")
            ip, port = "", ""
            try:
                from stun import get_ip_info
                nat, ip, port = get_ip_info()
            except Exception:
                pass
            yield Static(f"[bold yellow]Your public address:[/] {ip}:{port}", id="pub-addr")
            yield Static("")
            yield Static("[bold]Enter friend's address:[/]")
            yield Input(id="peer-addr", placeholder="192.168.1.105:5050")
            yield Static("")
            yield Horizontal(
                Button("Back", id="back-btn"),
                Button("Connect", id="connect-btn", variant="primary"),
            )

    def on_button_pressed(self, event):
        if event.button.id == "back-btn":
            self.app.pop_screen()
        elif event.button.id == "connect-btn":
            addr = self.query_one("#peer-addr").value.strip()
            parts = addr.rsplit(":", 1)
            if len(parts) == 2 and parts[1].isdigit():
                peer_ip = parts[0]
                peer_port = int(parts[1])
                if hasattr(self.engine.transport, "set_peer"):
                    self.engine.transport.set_peer(peer_ip, peer_port)
                self.app.pop_screen()
                self.app.notify("Connecting...", severity="information")
            else:
                self.app.notify("Invalid address. Format: IP:PORT", severity="error")


class ChatScreen(Screen):
    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+f", "send_file", "File"),
        Binding("ctrl+v", "send_clip", "Clip"),
        Binding("ctrl+s", "open_settings", "Settings"),
        Binding("ctrl+n", "connect_new", "Connect"),
        Binding("ctrl+l", "clear_chat", "Clear"),
    ]

    def __init__(self):
        super().__init__()
        self.engine = ChatEngine(
            on_message=self._handle_msg,
            on_status=self._handle_status,
            on_file_progress=self._handle_file_progress,
        )
        self._message_history = []
        self._connection_status = "connecting"
        self._lock = threading.Lock()

    def compose(self):
        cfg = config.load()
        yield Header(show_clock=True)
        with Container():
            yield RichLog(id="chat", wrap=True, highlight=True)
            with Horizontal(id="input-row"):
                yield Input(id="input", placeholder="Type message...")
                yield Button("Send", id="send-btn", variant="primary")
                yield Button("📎", id="file-btn")
                yield Button("📋", id="clip-btn")
                yield Button("⚙", id="settings-btn")
            yield Static(f"Mode: {cfg['mode'].upper()} | Ctrl+Q:Quit  /cmd  Ctrl+F:File  Ctrl+S:Settings", id="status-bar")

    def on_mount(self):
        self.update_status(config.get("mode", "lan").upper(), "connecting")
        self.start_engine()

    @work(thread=True, exclusive=True)
    def start_engine(self):
        ok = self.engine.start()
        if not ok:
            self._add_system_msg("Connection failed. Check settings.")

    def _handle_msg(self, msg: dict):
        try:
            self.app.call_from_thread(lambda: self._display_message(msg))
        except RuntimeError:
            self._display_message(msg)

    def _handle_status(self, text: str):
        try:
            self.app.call_from_thread(lambda: self._add_system_msg(text))
        except RuntimeError:
            self._add_system_msg(text)

    def _handle_file_progress(self, file_id, name, current, total):
        try:
            self.app.call_from_thread(lambda: self._show_progress(name, current, total))
        except RuntimeError:
            self._show_progress(name, current, total)

    def _display_message(self, msg: dict):
        cfg = config.load()
        msg_type = msg.get("type", "")
        data = msg.get("data", "")
        sender = msg.get("sender", "peer")
        ts = msg.get("time", datetime.now().strftime("%H:%M"))
        show_ts = cfg.get("show_timestamps", True)

        if msg_type == "text":
            self._add_msg(sender, data, ts, show_ts)
        elif msg_type == "clip":
            self._add_clip_msg(sender, data, ts, show_ts)
        elif msg_type == "file_meta":
            if isinstance(data, dict):
                self._add_file_meta(sender, data["name"], data["size"], ts, show_ts)
        elif msg_type == "ping":
            self.engine.transport.send(p.pong_msg())
            self._add_system_msg("ping received")
        elif msg_type == "pong":
            self._add_system_msg("pong received")

    def _add_msg(self, sender, text, ts, show_ts=True):
        timestamp = f"[dim]{ts}[/] " if show_ts else ""
        if sender == config.get("display_name", "") or sender.lower() in ("you", "", "me"):
            rendered = Text.from_markup(f"{timestamp}[bold blue]You:[/] {text}")
        else:
            rendered = Text.from_markup(f"{timestamp}[bold green]{sender}:[/] {text}")
        chat = self.query_one("#chat")
        chat.write(rendered)

    def _add_clip_msg(self, sender, text, ts, show_ts=True):
        timestamp = f"[dim]{ts}[/] " if show_ts else ""
        rendered = Text.from_markup(
            f"{timestamp}[bold magenta]{sender} sent clipboard:[/] {text}"
        )
        self.query_one("#chat").write(rendered)

    def _add_file_meta(self, sender, name, size, ts, show_ts=True):
        from .engine import _fmt_size
        timestamp = f"[dim]{ts}[/] " if show_ts else ""
        rendered = Text.from_markup(
            f"{timestamp}[bold cyan]{sender} sent file:[/] {name} ({_fmt_size(size)})"
        )
        self.query_one("#chat").write(rendered)

    def _add_system_msg(self, text: str):
        rendered = Text.from_markup(f"[dim yellow]{text}[/]")
        self.query_one("#chat").write(rendered)

    def _show_progress(self, name, current, total):
        pct = int(current / total * 100) if total else 0
        bar = "█" * (pct // 5) + "░" * (20 - pct // 5)
        rendered = Text.from_markup(f"[cyan]  {name}: [{bar}] {pct}%[/]")
        chat = self.query_one("#chat")
        chat.write(rendered)

    def update_status(self, mode_text, status):
        color = {"connected": "green", "connecting": "yellow", "disconnected": "red"}.get(status, "yellow")
        self.query_one("#status-bar").update(
            f"Mode: {mode_text} | [{color}]● {status.upper()}[/] | Ctrl+Q:Quit  /cmd  Ctrl+F:File  Ctrl+S:Settings"
        )

    def action_quit(self):
        self.engine.close()
        self.app.exit()

    def action_open_settings(self):
        self.app.push_screen(SettingsScreen())

    def action_connect_new(self):
        cfg = config.load()
        if cfg["mode"] == "p2p":
            self.app.push_screen(ConnectCodeScreen(self.engine))
        else:
            self.app.push_screen(LanSetupScreen())

    def action_clear_chat(self):
        self.query_one("#chat").clear()

    def action_send_clip(self):
        try:
            import pyperclip
            clip_text = pyperclip.paste()
            if clip_text.strip():
                self.engine.send_clip(clip_text)
                self._add_system_msg("clipboard sent")
        except Exception:
            self._add_system_msg("clipboard unavailable (install pyperclip)")

    def action_send_file(self):
        filepath = self._pick_file()
        if filepath:
            self.engine.send_file(filepath)

    def _pick_file(self):
        try:
            import subprocess
            result = subprocess.run(
                ["sh", "-c", 'ls -1 | fzf --prompt="Select file: " 2>/dev/null || ls -1 | head -20'],
                capture_output=True, text=True, timeout=10
            )
            files = [f for f in result.stdout.strip().split("\n") if f]
            if files:
                return files[0]
        except Exception:
            pass
        return None

    @on(Button.Pressed, "#send-btn")
    def on_send_click(self):
        self._do_send()

    @on(Button.Pressed, "#file-btn")
    def on_file_click(self):
        self.action_send_file()

    @on(Button.Pressed, "#clip-btn")
    def on_clip_click(self):
        self.action_send_clip()

    @on(Button.Pressed, "#settings-btn")
    def on_settings_click(self):
        self.action_open_settings()

    @on(Input.Submitted, "#input")
    def on_input_submit(self):
        self._do_send()

    def _do_send(self):
        inp = self.query_one("#input")
        text = inp.value.strip()
        if not text:
            return
        inp.clear()

        if text.startswith("/"):
            cmd = text[1:].strip().lower()
            if cmd == "exit":
                self.action_quit()
            elif cmd == "clear":
                self.action_clear_chat()
            elif cmd == "ping":
                self.engine.ping()
                self._add_system_msg("ping sent")
            elif cmd == "time":
                now = datetime.now().strftime("%H:%M:%S")
                self._add_system_msg(f"time: {now}")
            elif cmd == "clip":
                self.action_send_clip()
            elif cmd.startswith("file ") or cmd.startswith("send "):
                fpath = cmd.split(" ", 1)[1] if " " in cmd else ""
                if fpath:
                    self.engine.send_file(fpath)
                else:
                    self.action_send_file()
            elif cmd == "setting" or cmd == "settings":
                self.action_open_settings()
            elif cmd == "connect":
                self.action_connect_new()
            elif cmd == "help":
                self._show_help()
            else:
                self._add_system_msg(f"unknown: {text}")
        else:
            self.engine.send_text(text)

    def _show_help(self):
        help_text = (
            "/exit        Quit\n"
            "/clear       Clear screen\n"
            "/ping        Check connection\n"
            "/time        Show current time\n"
            "/clip        Send clipboard\n"
            "/file PATH   Send a file\n"
            "/setting     Open settings\n"
            "/connect     Connect to new peer\n"
            "/help        Show this help"
        )
        self._add_system_msg(help_text)


class LTApp(App):
    TITLE = "LT — Local Text"
    CSS = """
    Screen {
        background: $surface;
    }
    #onboarding, #lan-setup, #pair-setup, #settings, #connect-code {
        padding: 2 4;
        height: auto;
    }
    #welcome {
        text-align: center;
        text-style: bold;
        padding: 1;
    }
    .hint {
        color: $text-muted;
        margin-bottom: 1;
    }
    #chat {
        height: 1fr;
        border: solid $primary;
        margin: 0 1;
    }
    #input-row {
        height: 3;
        margin: 0 1;
        dock: bottom;
    }
    #input {
        width: 1fr;
    }
    #send-btn {
        width: 8;
        margin-left: 1;
    }
    #file-btn, #clip-btn, #settings-btn {
        width: 4;
        margin-left: 1;
    }
    #status-bar {
        height: 1;
        dock: bottom;
        content-align: center middle;
        color: $text-muted;
    }
    #settings-title {
        text-align: center;
        text-style: bold;
        padding: 1;
    }
    Button {
        margin: 1 1;
    }
    Select {
        margin-bottom: 1;
    }
    Checkbox {
        margin-bottom: 1;
    }
    """

    def on_mount(self):
        if config.is_configured():
            self.push_screen(ChatScreen())
        else:
            self.push_screen(OnboardingScreen())

    def action_quit(self):
        self.exit()


def run():
    app = LTApp()
    app.run()


if __name__ == "__main__":
    run()
