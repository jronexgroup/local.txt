import json
import socket
import threading
import time
from collections import defaultdict

from . import config
from . import protocol as p


class Transport:
    def __init__(self, on_message=None, on_status=None):
        self.on_message = on_message
        self.on_status = on_status
        self.running = False
        self._thread = None

    def connect(self):
        raise NotImplementedError

    def send(self, data: str):
        raise NotImplementedError

    def close(self):
        raise NotImplementedError

    def _emit_message(self, line: str):
        msg = p.unpack(line)
        if msg and self.on_message:
            self.on_message(msg)

    def _emit_status(self, text: str):
        if self.on_status:
            self.on_status(text)


class LANTCPTransport(Transport):
    def __init__(self, host, port, on_message=None, on_status=None):
        super().__init__(on_message, on_status)
        self.host = host
        self.port = port
        self.sock = None
        self.buf = ""

    def connect(self):
        result = {"sock": None, "ok": False}

        def try_connect():
            for _ in range(15):
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(2)
                    s.connect((self.host, self.port))
                    s.settimeout(None)
                    result["sock"] = s
                    result["ok"] = True
                    return
                except (ConnectionRefusedError, socket.timeout, OSError):
                    time.sleep(1)

        def try_listen():
            try:
                server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                server.bind(("0.0.0.0", self.port))
                server.listen(1)
                server.settimeout(2)
                for _ in range(20):
                    if result["ok"]:
                        server.close()
                        return
                    try:
                        conn, addr = server.accept()
                        if not result["ok"]:
                            result["sock"] = conn
                            result["ok"] = True
                        else:
                            conn.close()
                        server.close()
                        return
                    except socket.timeout:
                        continue
                server.close()
            except OSError:
                pass

        t1 = threading.Thread(target=try_connect, daemon=True)
        t2 = threading.Thread(target=try_listen, daemon=True)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        if not result["ok"]:
            return False

        self.sock = result["sock"]
        self._emit_status("connected")
        self.running = True
        self._thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._thread.start()
        return True

    def _recv_loop(self):
        while self.running:
            if not self.sock:
                time.sleep(0.1)
                continue
            try:
                data = self.sock.recv(65536)
                if not data:
                    raise ConnectionResetError
                self.buf += data.decode()
                while "\n" in self.buf:
                    line, self.buf = self.buf.split("\n", 1)
                    self._emit_message(line)
            except (ConnectionResetError, BrokenPipeError, OSError):
                self._emit_status("disconnected")
                if not self.running:
                    break
                self._emit_status("reconnecting")
                if self._reconnect():
                    self._emit_status("connected")
                    self.buf = ""
                else:
                    break

    def _reconnect(self):
        for _ in range(30):
            if not self.running:
                return False
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(3)
                s.connect((self.host, self.port))
                s.settimeout(None)
                self.sock = s
                return True
            except (ConnectionRefusedError, socket.timeout, OSError):
                time.sleep(2)
        return False

    def send(self, data: str):
        if not self.sock:
            return False
        try:
            self.sock.sendall(data.encode())
            return True
        except (BrokenPipeError, ConnectionResetError, OSError):
            return False

    def close(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass


class P2PTransport(Transport):
    def __init__(self, password, stun_server="stun.l.google.com:19302", on_message=None, on_status=None):
        super().__init__(on_message, on_status)
        self.password = password
        self.stun_server = stun_server
        self.sock = None
        self.peer_addr = None
        self.public_ip = None
        self.public_port = None
        self.buf = defaultdict(bytes)
        self.seq_recv = {}
        self.seq_send = 0
        self.lock = threading.Lock()

    def get_public_addr(self):
        from stun import get_ip_info
        nat_type, ip, port = get_ip_info(stun_host=self.stun_server.split(":")[0],
                                          stun_port=int(self.stun_server.split(":")[1]))
        self.public_ip = ip
        self.public_port = port
        return ip, port, nat_type

    def _send_packet(self, data: bytes, addr):
        try:
            self.sock.sendto(data, addr)
            return True
        except OSError:
            return False

    def _recv_packet(self, timeout=1):
        try:
            self.sock.settimeout(timeout)
            data, addr = self.sock.recvfrom(65536)
            return data, addr
        except socket.timeout:
            return None, None
        except OSError:
            return None, None

    def connect(self):
        self.get_public_addr()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        bind_port = config.get("p2p_port", 0)
        self.sock.bind(("0.0.0.0", bind_port or 0))
        if not bind_port:
            config.set_key("p2p_port", self.sock.getsockname()[1])

        self._emit_status(f"Your public address: {self.public_ip}:{self.public_port}")
        self._emit_status("Share this with your peer, then enter their address when they reply")

        return True

    def set_peer(self, peer_ip, peer_port):
        self.peer_addr = (peer_ip, peer_port)
        self._emit_status("connecting")
        self.running = True
        self._thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._thread.start()
        self._emit_status("connected")
        return True

    def _recv_loop(self):
        while self.running:
            data, addr = self._recv_packet(2)
            if data is None:
                continue
            if data == b"\x06":  # ACK
                continue
            if data.startswith(b"\x01"):
                seq = int.from_bytes(data[1:5], "big")
                self._send_packet(b"\x06" + data[1:5], addr)
                payload = data[5:]
                self.buf[addr].update({seq: payload})
                continue
            self._emit_message(data.decode())

    def send(self, data: str):
        if not self.sock or not self.peer_addr:
            return False
        payload = data.encode()
        seq = self.seq_send
        self.seq_send += 1
        packet = b"\x01" + seq.to_bytes(4, "big") + payload
        for _ in range(3):
            self._send_packet(packet, self.peer_addr)
            ack_data, _ = self._recv_packet(1)
            if ack_data and ack_data.startswith(b"\x06"):
                ack_seq = int.from_bytes(ack_data[1:5], "big")
                if ack_seq == seq:
                    return True
        return False

    def close(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass


class TorTransport(Transport):
    def __init__(self, password, socks_port=9050, control_port=9051, on_message=None, on_status=None):
        super().__init__(on_message, on_status)
        self.password = password
        self.socks_port = socks_port
        self.control_port = control_port
        self.sock = None
        self.buf = ""
        self.onion_addr = None

    def connect(self):
        self._emit_status("connecting")
        self.running = True
        self._thread = threading.Thread(target=self._recv_loop, daemon=True)
        self._thread.start()
        return True

    def start_hidden_service(self):
        try:
            from stem.control import Controller
            with Controller.from_port(port=self.control_port) as controller:
                controller.authenticate()
                service = controller.create_hidden_service(
                    {config.get("port", 5050): config.get("port", 5050)},
                    await_publication=True,
                )
                self.onion_addr = f"{service.service_id}.onion"
                self._emit_status(f"Your .onion: {self.onion_addr}:{config.get('port', 5050)}")
                return self.onion_addr
        except Exception as e:
            self._emit_status(f"Tor error: {e}")
            return None

    def connect_to_onion(self, onion_addr, port):
        try:
            import socks
            s = socks.socksocket()
            s.set_proxy(socks.SOCKS5, "127.0.0.1", self.socks_port)
            s.settimeout(10)
            s.connect((onion_addr, port))
            s.settimeout(None)
            self.sock = s
            self._emit_status("connected")
            return True
        except Exception as e:
            self._emit_status(f"Connection error: {e}")
            return False

    def _recv_loop(self):
        import socks
        while self.running:
            if not self.sock:
                time.sleep(0.5)
                continue
            try:
                data = self.sock.recv(65536)
                if not data:
                    raise ConnectionResetError
                self.buf += data.decode()
                while "\n" in self.buf:
                    line, self.buf = self.buf.split("\n", 1)
                    self._emit_message(line)
            except (ConnectionResetError, BrokenPipeError, OSError, socks.SocksError):
                self._emit_status("disconnected")
                time.sleep(3)
                if not self.running:
                    break

    def send(self, data: str):
        if not self.sock:
            return False
        try:
            self.sock.sendall(data.encode())
            return True
        except (BrokenPipeError, ConnectionResetError, OSError):
            return False

    def close(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass


def create_transport(mode=None, on_message=None, on_status=None):
    cfg = config.load()
    mode = mode or cfg["mode"]

    if mode == "lan":
        return LANTCPTransport(
            host=cfg["peer_ip"],
            port=cfg["port"],
            on_message=on_message,
            on_status=on_status,
        )
    elif mode == "p2p":
        return P2PTransport(
            password=cfg["pair_password"],
            stun_server=cfg.get("stun_server", "stun.l.google.com:19302"),
            on_message=on_message,
            on_status=on_status,
        )
    elif mode == "tor":
        return TorTransport(
            password=cfg["pair_password"],
            socks_port=cfg.get("tor_socks_port", 9050),
            control_port=cfg.get("tor_control_port", 9051),
            on_message=on_message,
            on_status=on_status,
        )
    return None
