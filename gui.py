import tkinter as tk
from tkinter import ttk, messagebox
import threading
import json
import os
import sys

# Import our KVM core classes
from kvm_core import KVMServer, KVMClient
from network import DiscoveryService
import time

# Theme Colors (Deep Charcoal & Neon Accents)
COLOR_BG = "#0A0A0C"          # Pitch black background
COLOR_CARD = "#121216"        # Deep panels
COLOR_BORDER = "#222228"      # Sleek card borders
COLOR_TEXT = "#E4E4EB"        # Cool white text
COLOR_MUTED = "#6B6B76"       # Dark grey muted text
COLOR_ACCENT = "#7C4DFF"      # Electric violet
COLOR_ACCENT_HOVER = "#9D75FF"# Lighter violet
COLOR_SUCCESS = "#00E676"     # Radiant emerald
COLOR_ERROR = "#FF1744"       # Neon red

CONFIG_FILE = "config.json"

class ModernButton(tk.Button):
    """Sleek flat modern button with custom colors and hover transitions."""
    def __init__(self, master, **kwargs):
        self.normal_bg = kwargs.pop("bg", COLOR_ACCENT)
        self.hover_bg = kwargs.pop("hover_bg", COLOR_ACCENT_HOVER)
        self.normal_fg = kwargs.pop("fg", "white")
        
        super().__init__(
            master,
            relief="flat",
            bd=0,
            bg=self.normal_bg,
            fg=self.normal_fg,
            activebackground=self.hover_bg,
            activeforeground=self.normal_fg,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
            padx=12,
            pady=6,
            **kwargs
        )
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def configure(self, cnf=None, **kwargs):
        if "hover_bg" in kwargs:
            self.hover_bg = kwargs.pop("hover_bg")
        if "bg" in kwargs:
            self.normal_bg = kwargs["bg"]
        super().configure(cnf, **kwargs)

    def config(self, cnf=None, **kwargs):
        self.configure(cnf, **kwargs)

    def _on_enter(self, e):
        super().configure(bg=self.hover_bg)

    def _on_leave(self, e):
        super().configure(bg=self.normal_bg)


class OmniControlGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("OmniControl // Premium Network KVM")
        self.root.geometry("850x680")
        self.root.configure(bg=COLOR_BG)
        
        # Prevent scaling layout issues
        self.root.option_add("*font", "SegoeUI 10")
        
        # State variables
        self.mode = tk.StringVar(value="server") # "server" or "client"
        self.passphrase = tk.StringVar(value="omnicontrol123")
        self.port = tk.StringVar(value="8900")
        self.client_server_ip = tk.StringVar(value="127.0.0.1")
        self.is_running = False
        
        # visual layout boundaries configuration
        self.layout_config = {
            "left": {"ip": "", "width": 1920, "height": 1080, "active": False},
            "right": {"ip": "", "width": 1920, "height": 1080, "active": False},
            "above": {"ip": "", "width": 1920, "height": 1080, "active": False},
            "below": {"ip": "", "width": 1920, "height": 1080, "active": False}
        }
        
        # References to running backend instances
        self.kvm_instance = None
        self.discovered_devices = {}
        self.discovery_service = None
        
        # Trace passphrase changes to dynamically restart discovery
        self.passphrase.trace_add("write", lambda *args: self.start_discovery())
        
        self.load_config()
        self.build_ui()
        
        # Secure exit handler to stop background discovery threads
        def on_close():
            self.stop_discovery()
            self.stop_kvm_service()
            self.root.destroy()
        self.root.protocol("WM_DELETE_WINDOW", on_close)

    def load_config(self):
        """Loads configuration from JSON file."""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    cfg = json.load(f)
                    self.passphrase.set(cfg.get("passphrase", "omnicontrol123"))
                    self.port.set(cfg.get("port", "8900"))
                    self.client_server_ip.set(cfg.get("server_ip", "127.0.0.1"))
                    self.mode.set(cfg.get("mode", "server"))
                    
                    saved_layout = cfg.get("layout", {})
                    for direction, data in saved_layout.items():
                        if direction in self.layout_config:
                            self.layout_config[direction].update(data)
            except Exception as e:
                print(f"Failed to load config.json: {e}")

    def save_config(self):
        """Saves current configurations to JSON file."""
        cfg = {
            "passphrase": self.passphrase.get(),
            "port": self.port.get(),
            "server_ip": self.client_server_ip.get(),
            "mode": self.mode.get(),
            "layout": self.layout_config
        }
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(cfg, f, indent=4)
        except Exception as e:
            self.log(f"Error saving config.json: {e}")

    def start_discovery(self):
        """Starts the background UDP auto-discovery service."""
        self.stop_discovery()
        self.discovered_devices = {}
        passphrase = self.passphrase.get().strip()
        if not passphrase:
            return
            
        self.discovery_service = DiscoveryService(
            node_type=self.mode.get(),
            passphrase=passphrase,
            callback=self.on_device_discovered
        )
        self.discovery_service.start()

    def stop_discovery(self):
        """Stops the auto-discovery service."""
        if self.discovery_service:
            try:
                self.discovery_service.stop()
            except Exception:
                pass
            self.discovery_service = None

    def on_device_discovered(self, payload: dict, ip: str):
        """Callback invoked when a new neighboring PC announces itself."""
        hostname = payload.get("hostname", "Unknown PC")
        is_new = ip not in self.discovered_devices
        
        self.discovered_devices[ip] = {
            "hostname": hostname,
            "timestamp": time.time()
        }
        
        # UI callback on discovery
        if is_new:
            if self.mode.get() == "client":
                current_ip = self.client_server_ip.get().strip()
                if current_ip in ["127.0.0.1", "", "192.168.1."]:
                    self.client_server_ip.set(ip)
                    self.log(f"AUTO-DISCOVERY: Dynamically populated Server IP to {ip} ({hostname})")
                else:
                    self.log(f"AUTO-DISCOVERY: Found Server '{hostname}' at {ip}")
            else:
                self.log(f"AUTO-DISCOVERY: Found Client '{hostname}' at {ip}")
                
        # Update client discovery status label if visible
        if hasattr(self, 'lbl_discovered') and self.lbl_discovered.winfo_exists():
            dev_text = ", ".join([f"{d['hostname']} ({k})" for k, d in self.discovered_devices.items()])
            self.lbl_discovered.configure(text=f"Discovered: {dev_text}", fg=COLOR_SUCCESS)

    def log(self, message: str):
        """Appends log text securely to the monitor console."""
        # Ensure UI interaction happens on the main thread safely
        self.root.after(0, self._safe_log, message)

    def _safe_log(self, message: str):
        self.log_area.configure(state="normal")
        # Color formatting based on prefix
        tag = None
        if "ERROR" in message or "failed" in message.lower():
            tag = "error"
        elif "success" in message.lower() or "connected" in message.lower() or "registered" in message.lower():
            tag = "success"
        elif "[Server]" in message or "[Client]" in message:
            tag = "muted"
            
        self.log_area.insert("end", f"▶ {message}\n", tag)
        self.log_area.see("end")
        self.log_area.configure(state="disabled")

    def build_ui(self):
        """Builds premium modern KVM control dashboard."""
        
        # Header banner
        header = tk.Frame(self.root, bg=COLOR_BG, height=60)
        header.pack(fill="x", padx=25, pady=(20, 10))
        
        lbl_title = tk.Label(
            header, 
            text="OMNICONTROL", 
            fg=COLOR_TEXT, 
            bg=COLOR_BG, 
            font=("Segoe UI", 18, "bold")
        )
        lbl_title.pack(side="left")
        
        lbl_ver = tk.Label(
            header, 
            text="v1.0.0 (Windows Low-Latency KVM)", 
            fg=COLOR_MUTED, 
            bg=COLOR_BG, 
            font=("Segoe UI", 9, "italic")
        )
        lbl_ver.pack(side="left", padx=10, pady=(6, 0))
        
        # Indicator Dot
        self.indicator_dot = tk.Label(
            header,
            text="● IDLE",
            fg=COLOR_MUTED,
            bg=COLOR_BG,
            font=("Segoe UI", 10, "bold")
        )
        self.indicator_dot.pack(side="right", pady=5)

        # Main grid container for left panel (inputs) and right panel (visual layout / console)
        main_body = tk.Frame(self.root, bg=COLOR_BG)
        main_body.pack(fill="both", expand=True, padx=25, pady=10)
        
        # --- LEFT PANEL (Settings) ---
        left_panel = tk.Frame(main_body, bg=COLOR_CARD, bd=1, highlightbackground=COLOR_BORDER, highlightthickness=1)
        left_panel.pack(side="left", fill="both", padx=(0, 10), pady=0, ipadx=15, ipady=15)
        
        tk.Label(left_panel, text="CONNECTION MODE", fg=COLOR_TEXT, bg=COLOR_CARD, font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=15, pady=(15, 10))
        
        # Styled mode select tab buttons
        tab_frame = tk.Frame(left_panel, bg=COLOR_CARD)
        tab_frame.pack(fill="x", padx=15, pady=(0, 15))
        
        self.btn_mode_srv = ModernButton(
            tab_frame,
            text="Server Mode",
            bg=COLOR_BORDER,
            hover_bg=COLOR_BORDER,
            command=lambda: self.switch_mode("server")
        )
        self.btn_mode_srv.pack(side="left", fill="x", expand=True, padx=(0, 2))
        
        self.btn_mode_cli = ModernButton(
            tab_frame,
            text="Client Mode",
            bg=COLOR_BORDER,
            hover_bg=COLOR_BORDER,
            command=lambda: self.switch_mode("client")
        )
        self.btn_mode_cli.pack(side="right", fill="x", expand=True, padx=(2, 0))
        
        # Form inputs panel
        self.form_frame = tk.Frame(left_panel, bg=COLOR_CARD)
        self.form_frame.pack(fill="both", expand=True, padx=15, pady=5)
        
        self.switch_mode(self.mode.get(), log_switch=False)
        
        # --- RIGHT PANEL (Screen Configuration and Logs) ---
        right_panel = tk.Frame(main_body, bg=COLOR_BG)
        right_panel.pack(side="right", fill="both", expand=True, padx=(10, 0))
        
        # 1. Screen boundaries layout visual grid
        self.layout_frame = tk.Frame(right_panel, bg=COLOR_CARD, bd=1, highlightbackground=COLOR_BORDER, highlightthickness=1)
        self.layout_frame.pack(fill="x", pady=(0, 15), ipadx=10, ipady=10)
        
        self.lbl_grid_title = tk.Label(
            self.layout_frame, 
            text="SCREEN BOUNDARY MAP CONFIGURATION", 
            fg=COLOR_TEXT, 
            bg=COLOR_CARD, 
            font=("Segoe UI", 10, "bold")
        )
        self.lbl_grid_title.pack(anchor="w", padx=10, pady=5)
        
        self.grid_container = tk.Frame(self.layout_frame, bg=COLOR_CARD)
        self.grid_container.pack(pady=10)
        
        self.build_visual_grid()
        
        # 2. Console Logs
        console_frame = tk.Frame(right_panel, bg=COLOR_CARD, bd=1, highlightbackground=COLOR_BORDER, highlightthickness=1)
        console_frame.pack(fill="both", expand=True, ipadx=10, ipady=10)
        
        tk.Label(console_frame, text="REAL-TIME MONITOR LOGS", fg=COLOR_TEXT, bg=COLOR_CARD, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=10, pady=5)
        
        self.log_area = tk.Text(
            console_frame, 
            bg=COLOR_BG, 
            fg="#BAC2DE", 
            relief="flat", 
            bd=0,
            font=("Consolas", 9),
            state="disabled",
            insertbackground="white",
            wrap="word"
        )
        self.log_area.pack(fill="both", expand=True, padx=10, pady=(5, 10))
        
        # Add coloring tags
        self.log_area.tag_configure("error", foreground=COLOR_ERROR)
        self.log_area.tag_configure("success", foreground=COLOR_SUCCESS)
        self.log_area.tag_configure("muted", foreground=COLOR_MUTED)

        # Footer control actions panel
        footer = tk.Frame(self.root, bg=COLOR_BG)
        footer.pack(fill="x", padx=25, pady=(10, 20))
        
        self.btn_toggle_kvm = ModernButton(
            footer,
            text="START OMNICONTROL KVM SERVICE",
            bg=COLOR_ACCENT,
            hover_bg=COLOR_ACCENT_HOVER,
            command=self.toggle_kvm_service
        )
        self.btn_toggle_kvm.pack(fill="x", ipady=10)
        
        self.log("OmniControl UI initialized successfully. Ready to connect.")

    def switch_mode(self, new_mode: str, log_switch: bool = True):
        """Handles switching tabs between Server and Client UI styles."""
        self.mode.set(new_mode)
        
        # Redraw mode buttons selection state
        if new_mode == "server":
            self.btn_mode_srv.configure(bg=COLOR_ACCENT, hover_bg=COLOR_ACCENT_HOVER)
            self.btn_mode_cli.configure(bg=COLOR_BORDER, hover_bg=COLOR_CARD)
        else:
            self.btn_mode_cli.configure(bg=COLOR_ACCENT, hover_bg=COLOR_ACCENT_HOVER)
            self.btn_mode_srv.configure(bg=COLOR_BORDER, hover_bg=COLOR_CARD)
            
        # Rebuild input form fields dynamically
        for child in self.form_frame.winfo_children():
            child.destroy()
            
        # Common inputs: Passphrase & Port
        tk.Label(self.form_frame, text="Security Passphrase", fg=COLOR_MUTED, bg=COLOR_CARD, font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(10, 2))
        ent_pass = tk.Entry(self.form_frame, textvariable=self.passphrase, bg=COLOR_BG, fg=COLOR_TEXT, relief="flat", insertbackground="white", bd=0, show="*")
        ent_pass.pack(fill="x", ipady=6, pady=(0, 10))
        
        tk.Label(self.form_frame, text="Port Number", fg=COLOR_MUTED, bg=COLOR_CARD, font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(5, 2))
        ent_port = tk.Entry(self.form_frame, textvariable=self.port, bg=COLOR_BG, fg=COLOR_TEXT, relief="flat", insertbackground="white", bd=0)
        ent_port.pack(fill="x", ipady=6, pady=(0, 10))
        
        # Mode-specific input: Server IP (Client only)
        if new_mode == "client":
            tk.Label(self.form_frame, text="Primary Server IP Address", fg=COLOR_MUTED, bg=COLOR_CARD, font=("Segoe UI", 9, "bold")).pack(anchor="w", pady=(5, 2))
            ent_ip = tk.Entry(self.form_frame, textvariable=self.client_server_ip, bg=COLOR_BG, fg=COLOR_TEXT, relief="flat", insertbackground="white", bd=0)
            ent_ip.pack(fill="x", ipady=6, pady=(0, 10))
            
            # Auto-discovery status label
            self.lbl_discovered = tk.Label(self.form_frame, text="Listening for nearby servers...", fg=COLOR_MUTED, bg=COLOR_CARD, font=("Segoe UI", 8, "italic"))
            self.lbl_discovered.pack(anchor="w", pady=(5, 10))
            
            # Hide boundary configuration on clients
            if hasattr(self, 'layout_frame') and self.layout_frame.winfo_exists():
                self.layout_frame.pack_forget()
        else:
            # Show boundary configuration on server
            if hasattr(self, 'layout_frame') and self.layout_frame.winfo_exists():
                self.layout_frame.pack(fill="x", pady=(0, 15), ipadx=10, ipady=10)
                
        # Start discovery listener for this mode
        self.start_discovery()
                
        if log_switch:
            self.log(f"Switched connection dashboard to {new_mode.upper()} mode.")

    def build_visual_grid(self):
        """Constructs interactive grid mapping of adjacent monitors."""
        for child in self.grid_container.winfo_children():
            child.destroy()
            
        # Primary local monitor in center (Non-interactive)
        srv_card = tk.Frame(self.grid_container, bg=COLOR_ACCENT, width=130, height=80)
        srv_card.pack_propagate(False)
        srv_card.grid(row=1, column=1, padx=10, pady=10)
        
        tk.Label(srv_card, text="PRIMARY SERVER\n(This PC)", fg="white", bg=COLOR_ACCENT, font=("Segoe UI", 9, "bold")).pack(expand=True)
        
        # Adjacent slots
        self.build_slot_button("above", row=0, col=1)
        self.build_slot_button("left", row=1, col=0)
        self.build_slot_button("right", row=1, col=2)
        self.build_slot_button("below", row=2, col=1)

    def build_slot_button(self, direction: str, row: int, col: int):
        """Builds a clickable panel to configure adjacent client screens."""
        cfg = self.layout_config[direction]
        
        card = tk.Frame(self.grid_container, bg=COLOR_BG, bd=1, highlightbackground=COLOR_BORDER, highlightthickness=1, width=130, height=80)
        card.pack_propagate(False)
        card.grid(row=row, column=col, padx=10, pady=10)
        
        if cfg["active"]:
            # Active configured screen details
            lbl_dir = tk.Label(card, text=direction.upper(), fg=COLOR_MUTED, bg=COLOR_BG, font=("Segoe UI", 8, "bold"))
            lbl_dir.pack(pady=(5, 0))
            
            lbl_ip = tk.Label(card, text=cfg["ip"], fg=COLOR_SUCCESS, bg=COLOR_BG, font=("Segoe UI", 8, "bold"))
            lbl_ip.pack(pady=2)
            
            btn_clear = tk.Button(
                card, 
                text="❌ Remove", 
                relief="flat", 
                bd=0, 
                bg=COLOR_BG, 
                fg=COLOR_ERROR, 
                font=("Segoe UI", 8),
                cursor="hand2",
                command=lambda d=direction: self.clear_slot(d)
            )
            btn_clear.pack(side="bottom", pady=2)
        else:
            # Clickable Add "+" slot
            btn_add = tk.Button(
                card, 
                text=f"+ Map {direction.capitalize()}", 
                relief="flat", 
                bd=0, 
                bg=COLOR_BG, 
                fg=COLOR_MUTED, 
                font=("Segoe UI", 8, "bold"),
                cursor="hand2",
                command=lambda d=direction: self.configure_slot_dialog(d)
            )
            btn_add.pack(fill="both", expand=True)

    def configure_slot_dialog(self, direction: str):
        """Opens miniature pop-up to configure IP and resolution properties."""
        dialog = tk.Toplevel(self.root)
        dialog.title(f"Configure {direction.capitalize()} Client PC")
        dialog.geometry("340x260")
        dialog.configure(bg=COLOR_BG)
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        
        # Center in parent
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 170
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 130
        dialog.geometry(f"+{x}+{y}")
        
        tk.Label(dialog, text=f"MAP NEIGHBORING {direction.upper()} SCREEN", fg=COLOR_TEXT, bg=COLOR_BG, font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=20, pady=(15, 10))
        
        # IP Field
        tk.Label(dialog, text="Client IP Address (or select discovered):", fg=COLOR_MUTED, bg=COLOR_BG, font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=20, pady=(5, 2))
        
        dev_list = [f"{d['hostname']} ({ip})" for ip, d in self.discovered_devices.items()]
        ent_ip = ttk.Combobox(dialog, values=dev_list)
        ent_ip.pack(fill="x", padx=20, ipady=2)
        
        # Populate current value with smart defaults
        current_ip = self.layout_config[direction]["ip"]
        if current_ip:
            matched_text = current_ip
            for ip, d in self.discovered_devices.items():
                if ip == current_ip:
                    matched_text = f"{d['hostname']} ({ip})"
                    break
            ent_ip.set(matched_text)
        elif dev_list:
            # Smart default 1: Auto-populate the first discovered client!
            ent_ip.set(dev_list[0])
        else:
            # Smart default 2: Get server's own active IP subnet prefix
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(('8.8.8.8', 80))
                local_ip = s.getsockname()[0]
                prefix = ".".join(local_ip.split(".")[:-1]) + "."
            except Exception:
                prefix = "192.168.1."
            finally:
                s.close()
            ent_ip.set(prefix)
        
        # Width / Height Fields
        res_frame = tk.Frame(dialog, bg=COLOR_BG)
        res_frame.pack(fill="x", padx=20, pady=10)
        
        tk.Label(res_frame, text="Width:", fg=COLOR_MUTED, bg=COLOR_BG, font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="w", pady=2)
        ent_w = tk.Entry(res_frame, width=8, bg=COLOR_CARD, fg=COLOR_TEXT, relief="flat", insertbackground="white", bd=0)
        ent_w.grid(row=0, column=1, padx=(5, 20), ipady=4)
        ent_w.insert(0, str(self.layout_config[direction]["width"]))
        
        tk.Label(res_frame, text="Height:", fg=COLOR_MUTED, bg=COLOR_BG, font=("Segoe UI", 8, "bold")).grid(row=0, column=2, sticky="w", pady=2)
        ent_h = tk.Entry(res_frame, width=8, bg=COLOR_CARD, fg=COLOR_TEXT, relief="flat", insertbackground="white", bd=0)
        ent_h.grid(row=0, column=3, padx=5, ipady=4)
        ent_h.insert(0, str(self.layout_config[direction]["height"]))
        
        def save_slot():
            raw_ip = ent_ip.get().strip()
            if "(" in raw_ip and ")" in raw_ip:
                ip = raw_ip.split("(")[-1].split(")")[0].strip()
            else:
                ip = raw_ip
            w_str = ent_w.get().strip()
            h_str = ent_h.get().strip()
            
            if not ip or ip == "192.168.1.":
                messagebox.showerror("Validation Error", "Please provide a valid client IP address.", parent=dialog)
                return
            try:
                w = int(w_str)
                h = int(h_str)
            except ValueError:
                messagebox.showerror("Validation Error", "Screen dimensions must be numbers.", parent=dialog)
                return
                
            self.layout_config[direction].update({
                "ip": ip,
                "width": w,
                "height": h,
                "active": True
            })
            self.save_config()
            self.build_visual_grid()
            dialog.destroy()
            self.log(f"Configured boundary screen '{direction}' at {ip} ({w}x{h})")
            
        ModernButton(dialog, text="SAVE CONFIGURATION", bg=COLOR_ACCENT, hover_bg=COLOR_ACCENT_HOVER, command=save_slot).pack(fill="x", padx=20, pady=15, ipady=4)

    def clear_slot(self, direction: str):
        """Removes configuration details mapped to a given slot direction."""
        self.layout_config[direction]["active"] = False
        self.save_config()
        self.build_visual_grid()
        self.log(f"Cleared screen boundary '{direction}' configuration mapping.")

    # --- KVM Service Toggle control logic ---

    def toggle_kvm_service(self):
        if self.is_running:
            self.stop_kvm_service()
        else:
            self.start_kvm_service()

    def start_kvm_service(self):
        mode = self.mode.get()
        passphrase = self.passphrase.get().strip()
        port_str = self.port.get().strip()
        
        if not passphrase:
            messagebox.showerror("Configuration Error", "Please provide a security passphrase.")
            return
        try:
            port = int(port_str)
        except ValueError:
            messagebox.showerror("Configuration Error", "Port must be a valid integer.")
            return
            
        self.is_running = True
        self.save_config()
        
        # Adjust UI states
        self.btn_toggle_kvm.configure(text="STOP OMNICONTROL KVM SERVICE", bg=COLOR_ERROR, hover_bg=COLOR_ERROR)
        self.indicator_dot.configure(text="● RUNNING", fg=COLOR_SUCCESS)
        
        # Instantiate server or client cores
        if mode == "server":
            # Filter active layout items
            active_layouts = {
                dir: data for dir, data in self.layout_config.items() if data["active"]
            }
            if not active_layouts:
                self.log("WARNING: No client screen boundaries configured. Edge crossing will not switch, but Ctrl+Alt+S toggle and clipboard monitoring remain active.")
                
            self.kvm_instance = KVMServer(
                port=port,
                passphrase=passphrase,
                layout_config=active_layouts,
                log_callback=self.log
            )
        else:
            server_ip = self.client_server_ip.get().strip()
            if not server_ip:
                messagebox.showerror("Configuration Error", "Please provide the Primary Server IP address.")
                self.stop_kvm_service()
                return
            self.kvm_instance = KVMClient(
                server_ip=server_ip,
                port=port,
                passphrase=passphrase,
                log_callback=self.log
            )
            
        try:
            self.kvm_instance.start()
            self.log(f"OmniControl {mode.upper()} service started successfully.")
        except Exception as e:
            self.log(f"Failed to start service: {e}")
            self.stop_kvm_service()

    def stop_kvm_service(self):
        self.is_running = False
        self.btn_toggle_kvm.configure(text="START OMNICONTROL KVM SERVICE", bg=COLOR_ACCENT, hover_bg=COLOR_ACCENT_HOVER)
        self.indicator_dot.configure(text="● IDLE", fg=COLOR_MUTED)
        
        if self.kvm_instance:
            try:
                self.kvm_instance.stop()
            except Exception as e:
                self.log(f"Error stopping KVM instance: {e}")
            self.kvm_instance = None
            
        self.log("OmniControl KVM service stopped.")


if __name__ == "__main__":
    # Elevated rights reminder on startup
    # Hooks work better when running as Admin
    root = tk.Tk()
    app = OmniControlGUI(root)
    
    # Check if running as Admin to output helpful log warning
    try:
        import ctypes
        is_admin = ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        is_admin = False
        
    if not is_admin:
        app.log("WARNING: Not running as Administrator. Windows may restrict input injection and auto-firewall configuration.")
    else:
        app.log("SUCCESS: Running with Administrator privileges. Zero input injection restrictions.")
        app.log("SUCCESS: Configuring Windows Firewall automatically...")
        
        # Auto-configure Windows Firewall in a background thread to prevent lag
        def auto_firewall():
            import subprocess
            try:
                # Add inbound rule for TCP 8900 (KVM input stream)
                subprocess.run('netsh advfirewall firewall add rule name="OmniControl KVM TCP" dir=in action=allow protocol=TCP localport=8900', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                # Add inbound rule for UDP 8901 (KVM auto-discovery)
                subprocess.run('netsh advfirewall firewall add rule name="OmniControl KVM UDP" dir=in action=allow protocol=UDP localport=8901', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                app.log("SUCCESS: Windows Firewall auto-configured for ports 8900 (TCP) and 8901 (UDP).")
            except Exception as e:
                app.log(f"WARNING: Failed to auto-configure Windows Firewall: {e}")
                
        threading.Thread(target=auto_firewall, daemon=True).start()
        
    root.mainloop()
