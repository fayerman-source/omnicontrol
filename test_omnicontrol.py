import unittest
import threading
import time
import socket
import secrets

import win32_helper as win32
from network import OmniCrypt, SecureSocket, DiscoveryService

class TestOmniControl(unittest.TestCase):
    
    def test_win32_clipboard(self):
        """Verifies native Win32 clipboard read and write APIs via ctypes."""
        original_text = win32.get_clipboard_text()
        test_string = f"OmniControl_KVM_Test_Token_{secrets.token_hex(4)}"
        
        try:
            success = win32.set_clipboard_text(test_string)
            self.assertTrue(success, "Failed to set clipboard text.")
            
            # Read it back and assert
            read_back = win32.get_clipboard_text()
            self.assertEqual(read_back, test_string, "Clipboard text did not match test string.")
        finally:
            # Restore user's original clipboard
            if original_text is not None:
                win32.set_clipboard_text(original_text)

    def test_win32_mouse_pos(self):
        """Verifies native Win32 mouse cursor reading and writing APIs via ctypes."""
        original_x, original_y = win32.get_mouse_position()
        
        try:
            # Shift mouse slightly
            test_x, test_y = original_x + 5, original_y + 5
            win32.set_mouse_position(test_x, test_y)
            time.sleep(0.05)  # Let Windows process the event
            
            new_x, new_y = win32.get_mouse_position()
            # On some scaling setups coordinates might vary by 1px
            self.assertTrue(abs(new_x - test_x) <= 2, f"Expected X near {test_x}, got {new_x}")
            self.assertTrue(abs(new_y - test_y) <= 2, f"Expected Y near {test_y}, got {new_y}")
        finally:
            # Restore mouse position
            win32.set_mouse_position(original_x, original_y)

    def test_omnicrypt_cipher(self):
        """Verifies the custom OmniCrypt SHA256 counter-mode stream cipher."""
        key = secrets.token_bytes(32)
        iv = secrets.token_bytes(16)
        
        secret_payload = b"OmniControl: Premium low-latency keystroke transmission"
        
        # Encrypt
        encrypted = OmniCrypt.encrypt_decrypt(secret_payload, key, iv)
        self.assertNotEqual(encrypted, secret_payload, "Encrypted payload should not match plain text.")
        
        # Decrypt (using identical XOR keystream)
        decrypted = OmniCrypt.encrypt_decrypt(encrypted, key, iv)
        self.assertEqual(decrypted, secret_payload, "Decrypted payload does not match original plain text.")

    def test_secure_socket_transmission(self):
        """Verifies loopback network packet transmission with transparent OmniCrypt encryption."""
        port = 28999
        passphrase = "test_passphrase_123"
        test_payload = {
            "type": "key",
            "vk": 65,
            "scan": 30,
            "flags": 0
        }
        
        server_sec_sock = None
        client_sec_sock = None
        handshake_event = threading.Event()
        received_packets = []
        
        def run_server():
            nonlocal server_sec_sock
            server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_sock.bind(('127.0.0.1', port))
            server_sock.listen(1)
            
            conn, addr = server_sock.accept()
            try:
                server_sec_sock = SecureSocket(conn, passphrase, is_server=True)
                handshake_event.set()
                
                # Receive packet
                packet = server_sec_sock.recv_packet()
                received_packets.append(packet)
            finally:
                conn.close()
                server_sock.close()

        # Start Server
        srv_thread = threading.Thread(target=run_server, daemon=True)
        srv_thread.start()
        time.sleep(0.1)  # Let server bind
        
        # Connect Client
        client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_sock.connect(('127.0.0.1', port))
        try:
            client_sec_sock = SecureSocket(client_sock, passphrase, is_server=False)
            handshake_event.wait(timeout=2.0)
            
            # Send test packet
            client_sec_sock.send_packet(test_payload)
            time.sleep(0.2)  # Let packet arrive
        finally:
            client_sock.close()
            
        # Verify receipt and integrity
        self.assertEqual(len(received_packets), 1, "Server did not receive the packet.")
        self.assertEqual(received_packets[0], test_payload, "Received packet content did not match transmitted payload.")

    def test_discovery_service(self):
        """Verifies the UDP broadcast auto-discovery service."""
        discovered = []
        event = threading.Event()
        
        def callback(payload, ip):
            discovered.append((payload, ip))
            event.set()
            
        passphrase = "test_discovery_passphrase"
        server_ds = DiscoveryService("server", passphrase, callback=None)
        client_ds = DiscoveryService("client", passphrase, callback=callback)
        
        try:
            client_ds.start()
            server_ds.start()
            
            # Wait for Client to discover Server broadcast
            event.wait(timeout=2.0)
        finally:
            server_ds.stop()
            client_ds.stop()
            
        self.assertTrue(len(discovered) >= 1, "Client failed to discover server beacon.")
        self.assertEqual(discovered[0][0]["hostname"], socket.gethostname(), "Hostname did not match.")


if __name__ == "__main__":
    print("==================================================")
    print("  RUNNING OMNICONTROL AUTO-VERIFICATION SUITE  ")
    print("==================================================")
    unittest.main()
