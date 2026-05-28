import threading
import time
import socket
import sys
import os
from ctypes import byref, sizeof, windll
from ctypes.wintypes import MSG

import win32_helper as win32
from network import SecureSocket

# Global references for hook callbacks (must persist in memory to avoid garbage collection)
_keyboard_hook_id = None
_mouse_hook_id = None
_hook_thread_id = None

class KVMServer:
    """
    Main Server core class running on the primary PC.
    Intercepts local input via low-level hooks, manages active client socket connections,
    tracks virtual mouse coordinates, and handles seamless edge-crossing and hotkeys.
    """
    def __init__(self, port: int, passphrase: str, layout_config: dict, log_callback=None):
        self.port = port
        self.passphrase = passphrase
        self.layout_config = layout_config  # e.g., {'left': {'ip': '...', 'width': 1920, 'height': 1080}}
        self.log_callback = log_callback or (lambda msg: print(f"[Server] {msg}"))
        
        self.running = False
        self.clients = {}  # direction -> SecureSocket
        self.active_client_dir = None  # 'left', 'right', 'above', 'below' or None (local)
        
        # Screen dimensions of primary server monitor
        self.server_w, self.server_h = win32.get_screen_size()
        self.center_x = self.server_w // 2
        self.center_y = self.server_h // 2
        
        # Virtual cursor state on active client
        self.virtual_x = 0
        self.virtual_y = 0
        self.client_w = 1920
        self.client_h = 1080
        
        # Clipboard state
        self.last_synced_clipboard = ""
        self.clipboard_thread = None
        
        # Hotkey tracking
        self.ctrl_pressed = False
        self.alt_pressed = False
        self.last_mouse_send_time = 0

    def log(self, message: str):
        self.log_callback(message)

    def start(self):
        self.running = True
        self.log(f"Starting server on port {self.port}...")
        
        # Start socket listening thread
        self.server_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.server_thread.start()
        
        # Start clipboard sync thread
        self.clipboard_thread = threading.Thread(target=self._clipboard_poll_loop, daemon=True)
        self.clipboard_thread.start()

        # Start Win32 hooks thread
        self.hooks_thread = threading.Thread(target=self._run_hooks_thread, daemon=True)
        self.hooks_thread.start()

    def stop(self):
        self.running = False
        self.log("Stopping server...")
        
        # Shutdown and close all client connections
        for direction, client in list(self.clients.items()):
            try:
                client.close()
            except Exception:
                pass
        self.clients.clear()
        self.active_client_dir = None
        
        # Break Windows Hooks Message Loop
        global _hook_thread_id
        if _hook_thread_id:
            # WM_QUIT = 0x0012
            win32.PostThreadMessage(_hook_thread_id, 0x0012, 0, 0)
            
        win32.unlock_cursor()

    def _listen_loop(self):
        """Listens for incoming client TCP connections."""
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            server_sock.bind(('0.0.0.0', self.port))
            server_sock.listen(5)
            self.log(f"Listening for connections on port {self.port}...")
            
            while self.running:
                server_sock.settimeout(1.0)
                try:
                    conn, addr = server_sock.accept()
                except socket.timeout:
                    continue
                except Exception as e:
                    if self.running:
                        self.log(f"Accept error: {e}")
                    break
                
                self.log(f"Client connecting from {addr[0]}...")
                threading.Thread(target=self._handle_client_handshake, args=(conn, addr), daemon=True).start()
        finally:
            server_sock.close()

    def _handle_client_handshake(self, conn: socket.socket, addr: tuple):
        """Handles security handshake and registers client."""
        try:
            sec_sock = SecureSocket(conn, self.passphrase, is_server=True)
            # Find direction based on configured client IP
            matched_direction = None
            for direction, cfg in self.layout_config.items():
                if cfg.get('ip') == addr[0] or addr[0] == '127.0.0.1':
                    matched_direction = direction
                    break
            
            if not matched_direction:
                # Fallback to any empty config slot
                for direction in ['left', 'right', 'above', 'below']:
                    if direction not in self.clients:
                        matched_direction = direction
                        break
            
            if matched_direction:
                self.clients[matched_direction] = sec_sock
                self.log(f"Client registered successfully as '{matched_direction}' boundary ({addr[0]})")
                
                # Retrieve client size configurations
                cfg = self.layout_config.get(matched_direction, {})
                cfg['width'] = cfg.get('width', 1920)
                cfg['height'] = cfg.get('height', 1080)
                self.layout_config[matched_direction] = cfg
                
                # Listen to incoming messages (like client clipboards or status)
                self._client_receive_loop(matched_direction, sec_sock)
            else:
                self.log(f"Rejected connection from {addr[0]} - no matching boundary config available.")
                conn.close()
        except Exception as e:
            self.log(f"Handshake failed with {addr[0]}: {e}")
            conn.close()

    def _client_receive_loop(self, direction: str, sec_sock: SecureSocket):
        """Receives messages from a connected client (e.g. Clipboard updates)."""
        try:
            while self.running:
                packet = sec_sock.recv_packet()
                if packet.get('type') == 'clipboard':
                    text = packet.get('text', '')
                    self.last_synced_clipboard = text
                    win32.set_clipboard_text(text)
                    self.log(f"Received clipboard text from {direction} client ({len(text)} chars)")
        except Exception as e:
            self.log(f"Client '{direction}' disconnected: {e}")
        finally:
            if direction in self.clients:
                del self.clients[direction]
            if self.active_client_dir == direction:
                self._switch_to_local()

    def _switch_to_client(self, direction: str):
        """Transitions focus and controls to specified client."""
        if direction not in self.clients:
            return
        
        self.active_client_dir = direction
        cfg = self.layout_config[direction]
        self.client_w = cfg['width']
        self.client_h = cfg['height']
        
        # Initialize virtual cursor on client boundary border
        if direction == 'left':
            self.virtual_x = self.client_w - 5
            self.virtual_y = self.center_y
        elif direction == 'right':
            self.virtual_x = 5
            self.virtual_y = self.center_y
        elif direction == 'above':
            self.virtual_x = self.center_x
            self.virtual_y = self.client_h - 5
        elif direction == 'below':
            self.virtual_x = self.center_x
            self.virtual_y = 5
            
        self.log(f"Switched control to '{direction}' client screen.")
        
        # Position physical cursor at center of server monitor
        win32.set_mouse_position(self.center_x, self.center_y)
        win32.lock_cursor_to_screen()

    def _switch_to_local(self):
        """Restores control to primary server PC."""
        prev_dir = self.active_client_dir
        self.active_client_dir = None
        win32.unlock_cursor()
        
        # Return physical cursor to boundary edge
        if prev_dir == 'left':
            win32.set_mouse_position(5, self.center_y)
        elif prev_dir == 'right':
            win32.set_mouse_position(self.server_w - 5, self.center_y)
        elif prev_dir == 'above':
            win32.set_mouse_position(self.center_x, 5)
        elif prev_dir == 'below':
            win32.set_mouse_position(self.center_x, self.server_h - 5)
        else:
            win32.set_mouse_position(self.center_x, self.center_y)
            
        self.log("Returned control to Server PC.")

    def _clipboard_poll_loop(self):
        """Polls the local clipboard to synchronize with clients."""
        while self.running:
            time.sleep(0.5)
            # Only poll clipboard when controlling local PC
            if not self.active_client_dir:
                try:
                    current_text = win32.get_clipboard_text()
                    if current_text and current_text != self.last_synced_clipboard:
                        self.last_synced_clipboard = current_text
                        # Send to all connected clients
                        packet = {"type": "clipboard", "text": current_text}
                        for client in list(self.clients.values()):
                            try:
                                client.send_packet(packet)
                            except Exception:
                                pass
                except Exception:
                    pass

    # --- Windows Low Level Hook Callback Logic ---

    def _run_hooks_thread(self):
        """Installs the keyboard and mouse hooks and runs the win32 event message loop."""
        global _keyboard_hook_id, _mouse_hook_id, _hook_thread_id
        
        _hook_thread_id = windll.kernel32.GetCurrentThreadId()
        
        # Define callback procedures
        self.keyboard_proc = win32.HookProc(self._keyboard_hook_cb)
        self.mouse_proc = win32.HookProc(self._mouse_hook_cb)
        
        # Install hooks
        _keyboard_hook_id = win32.SetWindowsHookEx(
            win32.WH_KEYBOARD_LL,
            self.keyboard_proc,
            None,
            0
        )
        _mouse_hook_id = win32.SetWindowsHookEx(
            win32.WH_MOUSE_LL,
            self.mouse_proc,
            None,
            0
        )
        
        if not _keyboard_hook_id or not _mouse_hook_id:
            self.log("ERROR: Failed to install low-level Win32 hooks!")
            return
            
        self.log("Global low-level input hooks installed successfully.")
        
        # Windows Message Pump
        msg = MSG()
        while win32.GetMessage(byref(msg), 0, 0, 0) != 0:
            win32.TranslateMessage(byref(msg))
            win32.DispatchMessage(byref(msg))
            
        # Clean up hooks upon exit
        win32.UnhookWindowsHookEx(_keyboard_hook_id)
        win32.UnhookWindowsHookEx(_mouse_hook_id)
        self.log("Low-level input hooks uninstalled cleanly.")

    def _keyboard_hook_cb(self, n_code, w_param, l_param) -> int:
        """Handles keyboard hook events."""
        if n_code >= 0:
            kbd = win32.KBDLLHOOKSTRUCT.from_address(l_param)
            
            # Keep track of hotkey modifier key states
            # VK_LCONTROL = 162, VK_RCONTROL = 163, VK_LMENU (LALT) = 164, VK_RMENU = 165
            is_down = (w_param == 256 or w_param == 260)  # WM_KEYDOWN or WM_SYSKEYDOWN
            
            if kbd.vkCode in [162, 163]:
                self.ctrl_pressed = is_down
            elif kbd.vkCode in [164, 165]:
                self.alt_pressed = is_down
                
            # Intercept hotkey Ctrl+Alt+S to instantly return control to server
            if self.ctrl_pressed and self.alt_pressed and kbd.vkCode == 83:  # 'S' key
                if is_down:
                    if self.active_client_dir:
                        self._switch_to_local()
                    else:
                        # Optional: Cycle or switch to first client
                        for dir in self.clients:
                            self._switch_to_client(dir)
                            break
                return 1 # Suppress hotkey event from going to local OS
                
            # Intercept hotkeys to switch directly
            if self.ctrl_pressed and self.alt_pressed and kbd.vkCode == 37:  # LEFT Arrow
                if is_down and not self.active_client_dir:
                    self._switch_to_client('left')
                return 1
            if self.ctrl_pressed and self.alt_pressed and kbd.vkCode == 39:  # RIGHT Arrow
                if is_down and not self.active_client_dir:
                    self._switch_to_client('right')
                return 1
                
            # If controlling client, intercept all keys and stream
            if self.active_client_dir:
                client = self.clients.get(self.active_client_dir)
                if client:
                    try:
                        # Extract transition state and keyboard flags
                        client.send_packet({
                            "type": "key",
                            "vk": kbd.vkCode,
                            "scan": kbd.scanCode,
                            "flags": kbd.flags
                        })
                    except Exception:
                        self._switch_to_local()
                return 1  # Suppress key from being processed on server PC
                
        return win32.CallNextHookEx(_keyboard_hook_id, n_code, w_param, l_param)

    def _mouse_hook_cb(self, n_code, w_param, l_param) -> int:
        """Handles mouse hook events."""
        if n_code >= 0:
            mouse = win32.MSLLHOOKSTRUCT.from_address(l_param)
            
            # Check edge crossing if we are in local control mode
            if not self.active_client_dir:
                # Check Left Edge (with 3px buffer)
                if mouse.pt.x <= 2 and 'left' in self.clients:
                    self._switch_to_client('left')
                    return 1
                # Check Right Edge (with 3px buffer)
                elif mouse.pt.x >= self.server_w - 3 and 'right' in self.clients:
                    self._switch_to_client('right')
                    return 1
                # Check Top Edge (with 3px buffer)
                elif mouse.pt.y <= 2 and 'above' in self.clients:
                    self._switch_to_client('above')
                    return 1
                # Check Bottom Edge (with 3px buffer)
                elif mouse.pt.y >= self.server_h - 3 and 'below' in self.clients:
                    self._switch_to_client('below')
                    return 1
            
            # If controlling client, intercept inputs and stream
            else:
                client = self.clients.get(self.active_client_dir)
                if client:
                    # Capture mouse move events
                    if w_param == 512:  # WM_MOUSEMOVE
                        # Calculate mouse delta (relative displacement)
                        dx = mouse.pt.x - self.center_x
                        dy = mouse.pt.y - self.center_y
                        
                        if dx != 0 or dy != 0:
                            # Update virtual cursor coordinates
                            self.virtual_x += dx
                            self.virtual_y += dy
                            
                            # Verify if virtual cursor crosses screen boundary back to server PC (with 2px return buffer)
                            returned = False
                            if self.active_client_dir == 'left' and self.virtual_x >= self.client_w - 2:
                                returned = True
                            elif self.active_client_dir == 'right' and self.virtual_x <= 2:
                                returned = True
                            elif self.active_client_dir == 'above' and self.virtual_y >= self.client_h - 2:
                                returned = True
                            elif self.active_client_dir == 'below' and self.virtual_y <= 2:
                                returned = True
                                
                            if returned:
                                self._switch_to_local()
                            else:
                                # Pin virtual cursor to boundary box
                                self.virtual_x = max(0, min(self.virtual_x, self.client_w))
                                self.virtual_y = max(0, min(self.virtual_y, self.client_h))
                                # Send network packet throttled to max 125Hz (8ms) to prevent network congestion
                                current_time = time.time()
                                if current_time - self.last_mouse_send_time >= 0.008:
                                    try:
                                        client.send_packet({
                                            "type": "mouse_move",
                                            "dx": self.virtual_x,
                                            "dy": self.virtual_y,
                                            "relative": False
                                        })
                                        self.last_mouse_send_time = current_time
                                    except Exception:
                                        self._switch_to_local()
                                    
                                # Snap physical cursor back to screen center to keep it bound
                                win32.set_mouse_position(self.center_x, self.center_y)
                                
                    # Capture mouse clicks/clicks/wheels
                    else:
                        # w_param holds the WM event code (e.g. WM_LBUTTONDOWN = 513)
                        # mouse.mouseData holds wheel direction / extra click properties
                        try:
                            client.send_packet({
                                "type": "mouse_click",
                                "event": w_param,
                                "data": mouse.mouseData
                            })
                        except Exception:
                            self._switch_to_local()
                            
                return 1 # Keep cursor locked on server screen and block local injection
                
        return win32.CallNextHookEx(_mouse_hook_id, n_code, w_param, l_param)


class KVMClient:
    """
    Client core class running on secondary PCs.
    Connects to the server, parses input event streams,
    and injects them natively into Windows using SendInput.
    """
    def __init__(self, server_ip: str, port: int, passphrase: str, log_callback=None):
        self.server_ip = server_ip
        self.port = port
        self.passphrase = passphrase
        self.log_callback = log_callback or (lambda msg: print(f"[Client] {msg}"))
        
        self.running = False
        self.sec_sock = None
        self.last_synced_clipboard = ""
        self.clipboard_thread = None
        self.active_control = False  # True when server is actively controlling us

    def log(self, message: str):
        self.log_callback(message)

    def start(self):
        self.running = True
        self.log(f"Connecting to KVM Server at {self.server_ip}:{self.port}...")
        
        # Start connection loop thread
        self.client_thread = threading.Thread(target=self._connection_loop, daemon=True)
        self.client_thread.start()
        
        # Start clipboard sync thread
        self.clipboard_thread = threading.Thread(target=self._clipboard_poll_loop, daemon=True)
        self.clipboard_thread.start()

    def stop(self):
        self.running = False
        if self.sec_sock:
            try:
                self.sec_sock.close()
            except Exception:
                pass
        self.log("Client stopped.")

    def _connection_loop(self):
        """Keeps attempting to connect to KVM server with backoff."""
        while self.running:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.connect((self.server_ip, self.port))
                self.log("Network socket connected. Initiating handshake...")
                
                self.sec_sock = SecureSocket(sock, self.passphrase, is_server=False)
                self.log("Secure TLS session established! Ready for inputs.")
                self.active_control = True
                
                # Receive input event streams
                self._receive_events()
            except Exception as e:
                self.active_control = False
                if self.running:
                    self.log(f"Connection lost / failed: {e}. Retrying in 3 seconds...")
                    time.sleep(3)
            finally:
                sock.close()

    def _receive_events(self):
        """Parses and executes event stream packets."""
        while self.running:
            packet = self.sec_sock.recv_packet()
            
            p_type = packet.get('type')
            
            if p_type == 'mouse_move':
                dx = packet.get('dx', 0)
                dy = packet.get('dy', 0)
                rel = packet.get('relative', True)
                win32.inject_mouse_move(dx, dy, relative=rel)
                
            elif p_type == 'mouse_click':
                event = packet.get('event', 0)
                data = packet.get('data', 0)
                
                # Map standard Windows mouse events to inject flags
                # WM_LBUTTONDOWN = 513 -> LEFTDOWN
                # WM_LBUTTONUP = 514 -> LEFTUP
                # WM_RBUTTONDOWN = 516 -> RIGHTDOWN
                # WM_RBUTTONUP = 517 -> RIGHTUP
                # WM_MBUTTONDOWN = 519 -> MIDDLEDOWN
                # WM_MBUTTONUP = 520 -> MIDDLEUP
                # WM_MOUSEWHEEL = 522 -> WHEEL
                # WM_MOUSEHWHEEL = 526 -> HWHEEL
                
                flags = 0
                mouse_data = 0
                
                if event == 513: flags = win32.MOUSEEVENTF_LEFTDOWN
                elif event == 514: flags = win32.MOUSEEVENTF_LEFTUP
                elif event == 516: flags = win32.MOUSEEVENTF_RIGHTDOWN
                elif event == 517: flags = win32.MOUSEEVENTF_RIGHTUP
                elif event == 519: flags = win32.MOUSEEVENTF_MIDDLEDOWN
                elif event == 520: flags = win32.MOUSEEVENTF_MIDDLEUP
                elif event == 522:
                    flags = win32.MOUSEEVENTF_WHEEL
                    # mouseData contains high word signed wheel delta
                    # Low level hook packs it in mouseData as high word (e.g. 120 << 16 = 7864320 or signed short)
                    # We extract it by shifting it back
                    high_word = (data >> 16) & 0xFFFF
                    # Convert to signed 16-bit
                    if high_word >= 0x8000:
                        high_word -= 0x10000
                    mouse_data = high_word
                elif event == 526:
                    flags = win32.MOUSEEVENTF_HWHEEL
                    high_word = (data >> 16) & 0xFFFF
                    if high_word >= 0x8000:
                        high_word -= 0x10000
                    mouse_data = high_word
                    
                if flags:
                    win32.inject_mouse_click(flags, mouse_data)
                    
            elif p_type == 'key':
                vk = packet.get('vk', 0)
                scan = packet.get('scan', 0)
                flags = packet.get('flags', 0)
                
                # In low-level keyboard hook:
                # flags & 1 == extended key
                # flags & 128 == key up event
                inject_flags = 0
                if flags & 1:
                    inject_flags |= win32.KEYEVENTF_EXTENDEDKEY
                if flags & 128:
                    inject_flags |= win32.KEYEVENTF_KEYUP
                    
                win32.inject_keyboard_key(vk, scan, inject_flags)
                
            elif p_type == 'clipboard':
                text = packet.get('text', '')
                self.last_synced_clipboard = text
                win32.set_clipboard_text(text)
                self.log(f"Synced clipboard text from server ({len(text)} chars)")

    def _clipboard_poll_loop(self):
        """Polls the local clipboard to synchronize with server."""
        while self.running:
            time.sleep(0.5)
            # Only poll when active connection exists and we have active focus
            if self.active_control:
                try:
                    current_text = win32.get_clipboard_text()
                    if current_text and current_text != self.last_synced_clipboard:
                        self.last_synced_clipboard = current_text
                        self.sec_sock.send_packet({
                            "type": "clipboard",
                            "text": current_text
                        })
                        self.log(f"Sent clipboard text to server ({len(current_text)} chars)")
                except Exception:
                    pass
