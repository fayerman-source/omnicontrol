import socket
import json
import struct
import hashlib
import secrets
import threading
import time

class OmniCrypt:
    """
    Symmetric stream cipher based on SHA256 in Counter (CTR) mode.
    Provides secure, low-latency encryption for local network KVM traffic
    without requiring external libraries or OpenSSL certificates.
    """
    @staticmethod
    def derive_key(passphrase: str, salt: bytes) -> bytes:
        """Derives a 32-byte key from a passphrase and salt using PBKDF2-HMAC-SHA256."""
        return hashlib.pbkdf2_hmac(
            'sha256',
            passphrase.encode('utf-8'),
            salt,
            iterations=1000,
            dklen=32
        )

    @staticmethod
    def encrypt_decrypt(data: bytes, key: bytes, iv: bytes) -> bytes:
        """
        Encrypts or decrypts bytes using a SHA-256 CTR-mode stream cipher.
        Since it is an XOR stream cipher, encryption and decryption are identical.
        """
        out = bytearray()
        counter = 0
        for i in range(0, len(data), 32):
            # Generate 32 bytes of keystream: SHA256(key + iv + counter)
            keystream_block = hashlib.sha256(
                key + iv + counter.to_bytes(4, byteorder='big')
            ).digest()
            
            chunk = data[i:i+32]
            for b, k in zip(chunk, keystream_block):
                out.append(b ^ k)
            counter += 1
        return bytes(out)

class SecureSocket:
    """
    Wrapper around a standard TCP socket to handle packet framing
    (length headers) and transparent OmniCrypt encryption.
    """
    def __init__(self, sock: socket.socket, passphrase: str, is_server: bool = False):
        self.sock = sock
        # Enable TCP_NODELAY to disable Nagle's algorithm for low-latency transmission
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.passphrase = passphrase
        self.key = None
        self.lock = threading.Lock()
        
        # Handshake: exchange salt and derive key
        if is_server:
            # Server generates random salt and sends it to client
            salt = secrets.token_bytes(16)
            self.sock.sendall(salt)
            self.key = OmniCrypt.derive_key(passphrase, salt)
        else:
            # Client receives salt and derives key
            salt = self._recv_all(16)
            self.key = OmniCrypt.derive_key(passphrase, salt)

    def _recv_all(self, n: int) -> bytes:
        """Helper to receive exactly n bytes from the socket."""
        data = bytearray()
        while len(data) < n:
            packet = self.sock.recv(n - len(data))
            if not packet:
                raise ConnectionError("Socket connection closed prematurely.")
            data.extend(packet)
        return bytes(data)

    def send_packet(self, payload: dict):
        """Encrypts and sends a JSON payload over the socket."""
        # Serialize to JSON and encode to bytes
        data_bytes = json.dumps(payload).encode('utf-8')
        
        # Generate random 16-byte IV for this packet
        iv = secrets.token_bytes(16)
        
        # Encrypt the data payload
        encrypted_data = OmniCrypt.encrypt_decrypt(data_bytes, self.key, iv)
        
        # Packet format: [4 bytes length of (IV + Encrypted Data)] + [16 bytes IV] + [Encrypted Data]
        total_len = len(iv) + len(encrypted_data)
        packet = struct.pack('!I', total_len) + iv + encrypted_data
        
        with self.lock:
            self.sock.sendall(packet)

    def recv_packet(self) -> dict:
        """Receives, decrypts, and deserializes a JSON payload."""
        # Read the 4-byte length header
        header = self._recv_all(4)
        total_len = struct.unpack('!I', header)[0]
        
        # Read the entire packet (16 bytes IV + encrypted data)
        packet_data = self._recv_all(total_len)
        
        # Extract IV and encrypted payload
        iv = packet_data[:16]
        encrypted_data = packet_data[16:]
        
        # Decrypt payload
        decrypted_bytes = OmniCrypt.encrypt_decrypt(encrypted_data, self.key, iv)
        
        # Deserialize JSON
        return json.loads(decrypted_bytes.decode('utf-8'))

    def close(self):
        """Closes the underlying socket safely."""
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        self.sock.close()


class DiscoveryService:
    """
    Symmetric UDP Broadcasting Auto-Discovery Service.
    Allows servers and clients to discover each other's IP addresses and hostnames
    seamlessly on the local network without manual entry.
    """
    UDP_PORT = 8901
    
    def __init__(self, node_type: str, passphrase: str, callback=None):
        """
        node_type: 'server' or 'client'
        passphrase: To prevent discovering unauthorized devices
        callback: Function invoked when a new device is discovered. Callback signature: callback(data: dict, ip: str)
        """
        self.node_type = node_type
        self.passphrase = passphrase
        self.callback = callback
        self.running = False
        
        self.broadcast_thread = None
        self.listener_thread = None
        self.broadcaster_sock = None
        self.listener_sock = None

    def start(self):
        self.running = True
        
        # 1. Start Listener Thread
        self.listener_thread = threading.Thread(target=self._run_listener, daemon=True)
        self.listener_thread.start()
        
        # 2. Start Broadcaster Thread
        self.broadcast_thread = threading.Thread(target=self._run_broadcaster, daemon=True)
        self.broadcast_thread.start()

    def stop(self):
        self.running = False
        if self.broadcaster_sock:
            try:
                self.broadcaster_sock.close()
            except Exception:
                pass
        if self.listener_sock:
            try:
                self.listener_sock.close()
            except Exception:
                pass

    def _run_broadcaster(self):
        self.broadcaster_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.broadcaster_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.broadcaster_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        hostname = socket.gethostname()
        pass_hash = hashlib.sha256(self.passphrase.encode('utf-8')).hexdigest()[:16]
        
        beacon = {
            "type": f"OMNICONTROL_{self.node_type.upper()}_BEACON",
            "hostname": hostname,
            "pass_hash": pass_hash
        }
        
        message = json.dumps(beacon).encode('utf-8')
        
        while self.running:
            try:
                # Broadcast to local subnet
                self.broadcaster_sock.sendto(message, ('255.255.255.255', self.UDP_PORT))
            except Exception:
                pass
            time.sleep(3.0)

    def _run_listener(self):
        self.listener_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.listener_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            self.listener_sock.bind(('0.0.0.0', self.UDP_PORT))
        except Exception:
            return
            
        pass_hash = hashlib.sha256(self.passphrase.encode('utf-8')).hexdigest()[:16]
        
        while self.running:
            try:
                data, addr = self.listener_sock.recvfrom(2048)
                ip = addr[0]
                
                payload = json.loads(data.decode('utf-8'))
                
                if payload.get("pass_hash") == pass_hash:
                    expected_beacon = "OMNICONTROL_SERVER_BEACON" if self.node_type == "client" else "OMNICONTROL_CLIENT_BEACON"
                    
                    if payload.get("type") == expected_beacon:
                        if self.callback:
                            self.callback(payload, ip)
            except Exception:
                pass
