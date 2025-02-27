import tkinter as tk
from tkinter import ttk
import socket
import threading
import random
import string
import pyaudio
import sys
import struct, math
import time

# Global audio parameters
CHUNK = 1024             # Audio samples per frame
FORMAT = pyaudio.paInt16 # 16-bit audio format
CHANNELS = 1             # Mono
RATE = 16000             # Sample rate in Hz

def get_volume(data):
    """Calculate RMS volume from audio data."""
    if not data:
        return 0
    count = len(data) // 2
    try:
        fmt = "<" + "h" * count
        samples = struct.unpack(fmt, data)
    except Exception:
        return 0
    sum_squares = sum(s * s for s in samples)
    rms = math.sqrt(sum_squares / count)
    return rms

def volume_to_color(rms):
    """
    Map RMS volume (0 to a threshold) to a color interpolating
    from light grey (#cccccc) to green (#00ff00).
    """
    max_rms = 2000  # threshold for full green
    ratio = min(rms / max_rms, 1.0)
    r = int(204 * (1 - ratio))
    g = int(204 + (51 * ratio))
    b = int(204 * (1 - ratio))
    return f'#{r:02x}{g:02x}{b:02x}'

class VoIPApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Local Privacy-Focused VoIP")
        self.root.geometry("800x600")
        self.root.configure(bg="#F5F5F5")  # soft light background

        # Configure a modern ttk style with flat buttons and Segoe UI fonts.
        self.style = ttk.Style()
        self.style.theme_use("clam")
        self.style.configure("TButton", font=("Segoe UI", 12), padding=6, relief="flat", background="#E0E0E0")
        self.style.map("TButton",
                       foreground=[('active', '#333333')],
                       background=[('active', '#D0D0D0')])
        self.style.configure("TLabel", font=("Segoe UI", 12), background="#F5F5F5")
        self.style.configure("Header.TLabel", font=("Segoe UI", 16, "bold"), background="#F5F5F5")
        self.style.configure("TEntry", font=("Segoe UI", 12), padding=4)

        # Session-only settings.
        self.username = None
        self.host_username = None  # For clients, set upon connection.
        self.input_device = None
        self.output_device = None
        self.room_code = None
        self.connected_users = []   # List of tuples: (username, role)
        self.client_sockets = {}    # For host: mapping client username -> socket.
        self.indicator_widgets = {} # Mapping username -> (canvas, oval id) for host view.
        self.call_indicator = None  # For client call view indicator.
        self.current_client_sock = None  # For clients, store the active TCP socket.
        self.is_host = False        # Flag: True if hosting; False if client.
        self.control_listener_running = False  # For client UDP control listener.
        self.chat_listener_running = False       # For chat UDP listener
        self.chat_history = []      # List to store chat history

        # New volume control settings:
        self.volume_factor = 1.0    # 1.0 == 100% volume
        self.muted = False

        # Frames for room view (persistent when hosting)
        self.details_frame = None  # Holds room details for host
        self.chat_frame = None     # Holds chat UI (persistent)

        # Room tab button variables.
        self.room_tab_button = None
        self.in_room = False

        self.py_audio = pyaudio.PyAudio()

        # Main window layout: left menu and right content area.
        self.menu_frame = tk.Frame(root, width=200, bg="#FFFFFF", bd=0, highlightthickness=0)
        self.menu_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(10, 5), pady=10)
        self.content_frame = tk.Frame(root, bg="#FFFFFF", bd=2, relief="flat")
        self.content_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 10), pady=10)

        self.create_menu_buttons()
        self.show_username_prompt()

    # Helper method to safely update widget properties
    def safe_update_itemconfig(self, canvas, oval, color):
        try:
            if canvas.winfo_exists():
                canvas.itemconfig(oval, fill=color)
        except tk.TclError:
            pass

    # --- New helper methods for volume control ---
    def scale_audio(self, data, volume):
        """Scale 16-bit audio samples by a volume factor."""
        count = len(data) // 2
        fmt = "<" + "h" * count
        samples = struct.unpack(fmt, data)
        scaled = []
        for s in samples:
            new_val = int(s * volume)
            if new_val > 32767:
                new_val = 32767
            elif new_val < -32768:
                new_val = -32768
            scaled.append(new_val)
        return struct.pack(fmt, *scaled)

    def set_volume(self, val):
        try:
            vol = float(val) / 100.0
            self.volume_factor = vol
        except Exception:
            pass

    def toggle_mute(self):
        self.muted = not self.muted

    # --- End new volume control methods ---

    def create_menu_buttons(self):
        """Create the static left-side menu buttons."""
        btn_home = ttk.Button(self.menu_frame, text="Home", command=self.show_home)
        btn_home.pack(pady=10, fill=tk.X, padx=10)
        btn_new_room = ttk.Button(self.menu_frame, text="New Room", command=self.create_new_room)
        btn_new_room.pack(pady=10, fill=tk.X, padx=10)
        btn_connect = ttk.Button(self.menu_frame, text="Connect", command=self.connect_to_room)
        btn_connect.pack(pady=10, fill=tk.X, padx=10)
        btn_settings = ttk.Button(self.menu_frame, text="Settings", command=self.open_settings)
        btn_settings.pack(pady=10, fill=tk.X, padx=10)
        btn_exit = ttk.Button(self.menu_frame, text="Exit", command=self.exit_app)
        btn_exit.pack(pady=10, fill=tk.X, padx=10)

    def add_room_tab(self):
        """Add a dynamic 'Room' tab button if not already present."""
        if not self.room_tab_button:
            self.room_tab_button = ttk.Button(self.menu_frame, text="Room", command=self.show_room_view)
            self.room_tab_button.pack(pady=10, fill=tk.X, padx=10)
            self.in_room = True

    def remove_room_tab(self):
        """Remove the dynamic 'Room' tab button."""
        if self.room_tab_button:
            self.room_tab_button.destroy()
            self.room_tab_button = None
            self.in_room = False

    def show_room_view(self):
        """Bring you back to the room view if you are in one."""
        if self.room_code is not None:
            if self.is_host:
                self.update_room_view()  # host: update details area (chat persists)
            else:
                self.show_client_call_view()

    def clear_content(self):
        """Remove all widgets from the content area."""
        for widget in self.content_frame.winfo_children():
            widget.destroy()

    def show_username_prompt(self):
        """Integrated username selection form."""
        self.clear_content()
        prompt_frame = tk.Frame(self.content_frame, bg="#FFFFFF")
        prompt_frame.pack(expand=True)
        ttk.Label(prompt_frame, text="Choose a Username:", style="Header.TLabel").pack(pady=10)
        username_entry = ttk.Entry(prompt_frame, width=30)
        username_entry.pack(pady=5)
        error_label = ttk.Label(prompt_frame, text="", foreground="red")
        error_label.pack(pady=5)

        def submit_username():
            name = username_entry.get().strip()
            if name:
                self.username = name
                self.host_username = name  # For later hosting.
                # Set default audio devices if not already chosen.
                inputs = self.get_audio_devices(input=True)
                outputs = self.get_audio_devices(input=False)
                if inputs and self.input_device is None:
                    self.input_device = int(inputs[0].split(":")[0])
                if outputs and self.output_device is None:
                    self.output_device = int(outputs[0].split(":")[0])
                self.show_home()
            else:
                error_label.config(text="Username cannot be empty.")

        ttk.Button(prompt_frame, text="Submit", command=submit_username).pack(pady=10)

    def show_home(self):
        """Display a home/welcome view."""
        self.clear_content()
        home_frame = tk.Frame(self.content_frame, bg="#FFFFFF")
        home_frame.pack(expand=True)
        if self.username:
            ttk.Label(home_frame, text=f"Welcome, {self.username}!", style="Header.TLabel").pack(pady=10)
        ttk.Label(home_frame, text="Select an option from the menu on the left.").pack(pady=5)

    def open_settings(self):
        """Display settings in the content area."""
        self.clear_content()
        settings_frame = tk.Frame(self.content_frame, bg="#FFFFFF")
        settings_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        ttk.Label(settings_frame, text="Settings", style="Header.TLabel").pack(pady=10)

        ttk.Label(settings_frame, text="Change Username:").pack(pady=5)
        username_entry = ttk.Entry(settings_frame, width=30)
        username_entry.insert(0, self.username)
        username_entry.pack(pady=5)
        msg_label = ttk.Label(settings_frame, text="")
        msg_label.pack(pady=5)

        def update_username():
            new_name = username_entry.get().strip()
            if new_name:
                self.username = new_name
                msg_label.config(text="Username updated!", foreground="green")
            else:
                msg_label.config(text="Username cannot be empty.", foreground="red")

        ttk.Button(settings_frame, text="Update Username", command=update_username).pack(pady=10)

        ttk.Label(settings_frame, text="Select Audio Input Device:").pack(pady=5)
        input_combo = ttk.Combobox(settings_frame, values=self.get_audio_devices(input=True))
        input_combo.pack(pady=5)
        ttk.Label(settings_frame, text="Select Audio Output Device:").pack(pady=5)
        output_combo = ttk.Combobox(settings_frame, values=self.get_audio_devices(input=False))
        output_combo.pack(pady=5)

        def update_audio_devices():
            try:
                self.input_device = int(input_combo.get().split(":")[0])
                self.output_device = int(output_combo.get().split(":")[0])
                msg_label.config(text="Audio devices updated!", foreground="green")
            except Exception:
                msg_label.config(text="Invalid selection.", foreground="red")

        ttk.Button(settings_frame, text="Update Audio Devices", command=update_audio_devices).pack(pady=10)

    def create_new_room(self):
        """Host creates a new room.
        
        If already in a room, it first closes that room (kicking clients and resetting chat)
        before creating a new one.
        """
        if self.room_code is not None:
            self.close_room()
            self.chat_history = []  # reset chat history
        self.clear_content()
        self.room_code = ''.join(random.choices(string.ascii_letters + string.digits, k=24))
        self.connected_users = [(self.username, "host")]
        self.is_host = True

        # Create two persistent frames: one for room details and one for chat.
        self.details_frame = tk.Frame(self.content_frame, bg="#FFFFFF")
        self.details_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=(20, 10))
        self.chat_frame = tk.Frame(self.content_frame, bg="#FFFFFF")
        self.chat_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 20))
        self.create_chat_ui(self.chat_frame)
        
        if not self.chat_listener_running:
            threading.Thread(target=self.udp_chat_listener, daemon=True).start()

        self.update_room_view()
        self.add_room_tab()
        threading.Thread(target=self.start_server, daemon=True).start()
        threading.Thread(target=self.udp_discovery_listener, daemon=True).start()
        self.poll_host_room_view()

    def poll_host_room_view(self):
        """Periodically update the host room details."""
        if self.is_host:
            self.update_room_view()
            self.root.after(2000, self.poll_host_room_view)

    def update_room_view(self):
        """Update the host room details (without disturbing the chat)."""
        if self.is_host and self.details_frame:
            for widget in self.details_frame.winfo_children():
                widget.destroy()
            ttk.Label(self.details_frame, text=f"Connected Users: {len(self.connected_users)}").pack(pady=5)
            ttk.Label(self.details_frame, text="Room Code:", style="Header.TLabel").pack(pady=(10, 0))
            room_code_entry = ttk.Entry(self.details_frame, font=("Segoe UI", 18, "bold"), justify="center", width=30)
            room_code_entry.insert(0, self.room_code)
            room_code_entry.config(state='readonly')
            room_code_entry.pack(pady=10)

            self.users_list_frame = tk.Frame(self.details_frame, bg="#FFFFFF")
            self.users_list_frame.pack(pady=10, fill=tk.BOTH, expand=True)
            for user, role in self.connected_users:
                user_frame = tk.Frame(self.users_list_frame, bg="#FFFFFF")
                user_frame.pack(fill=tk.X, pady=2)
                label_text = user + (" (Host)" if role == "host" else " (Client)")
                ttk.Label(user_frame, text=label_text).pack(side=tk.LEFT, padx=5)
                if user not in self.indicator_widgets:
                    canvas = tk.Canvas(user_frame, width=15, height=15, bg="#FFFFFF", highlightthickness=0)
                    oval = canvas.create_oval(2, 2, 13, 13, fill="#cccccc", outline="")
                    canvas.pack(side=tk.RIGHT, padx=10)
                    self.indicator_widgets[user] = (canvas, oval)
                else:
                    canvas, oval = self.indicator_widgets[user]
                    canvas.itemconfig(oval, fill="#cccccc")
            ttk.Button(self.details_frame, text="Close Room", command=self.close_room).pack(pady=10)
            self.broadcast_user_list()

    def show_client_call_view(self):
        """Client call view with host info, connected users, chat, and volume controls."""
        self.clear_content()
        call_frame = tk.Frame(self.content_frame, bg="#FFFFFF")
        call_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)
        header_frame = tk.Frame(call_frame, bg="#FFFFFF")
        header_frame.pack(pady=5)
        ttk.Label(header_frame, text=f"Host: {self.host_username}").pack(side=tk.LEFT, padx=5)
        indicator_canvas = tk.Canvas(header_frame, width=15, height=15, highlightthickness=0, bg="#FFFFFF")
        oval = indicator_canvas.create_oval(2, 2, 13, 13, fill="#cccccc", outline="")
        indicator_canvas.pack(side=tk.LEFT, padx=5)
        self.call_indicator = (indicator_canvas, oval)
        ttk.Label(call_frame, text="Connected Users:", style="Header.TLabel").pack(pady=(10, 0))
        self.client_users_frame = tk.Frame(call_frame, bg="#FFFFFF")
        self.client_users_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.update_client_users_view()
        self.create_chat_ui(call_frame)
        if not self.chat_listener_running:
            threading.Thread(target=self.udp_chat_listener, daemon=True).start()
        ttk.Button(call_frame, text="End Call",
                   command=lambda: self.end_call(self.current_client_sock, call_frame, "client")).pack(pady=5)
        if not self.control_listener_running:
            threading.Thread(target=self.udp_control_listener, daemon=True).start()
            self.control_listener_running = True
        self.poll_client_users_view()

    def poll_client_users_view(self):
        """Periodically update the client call view's connected-users list."""
        if not self.is_host:
            self.update_client_users_view()
            self.root.after(2000, self.poll_client_users_view)

    def update_client_users_view(self):
        """Update the connected-users list in the client call view."""
        if hasattr(self, 'client_users_frame') and self.client_users_frame:
            for widget in self.client_users_frame.winfo_children():
                widget.destroy()
            for user, role in self.connected_users:
                label_text = user + (" (Host)" if role == "host" else " (Client)")
                ttk.Label(self.client_users_frame, text=label_text).pack(anchor="w", pady=2)

    def create_chat_ui(self, parent):
        """
        Create a chat box UI with a text display, entry field, send button,
        plus a volume slider and mute button.
        """
        chat_container = tk.Frame(parent, bg="#FFFFFF", bd=2, relief="groove")
        chat_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        text_frame = tk.Frame(chat_container)
        text_frame.pack(fill=tk.BOTH, expand=True)
        chat_text = tk.Text(text_frame, wrap=tk.WORD, height=10, state=tk.DISABLED, font=("Segoe UI", 12))
        chat_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar = ttk.Scrollbar(text_frame, command=chat_text.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        chat_text.config(yscrollcommand=scrollbar.set)
        for msg in self.chat_history:
            chat_text.config(state=tk.NORMAL)
            chat_text.insert(tk.END, msg + "\n")
            chat_text.config(state=tk.DISABLED)
        self.chat_text = chat_text

        entry_frame = tk.Frame(chat_container, bg="#FFFFFF")
        entry_frame.pack(fill=tk.X)
        chat_entry = ttk.Entry(entry_frame, font=("Segoe UI", 12))
        chat_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5), pady=5)
        chat_entry.bind("<Return>", lambda event: self.send_chat_message())
        self.chat_entry = chat_entry
        send_button = ttk.Button(entry_frame, text="Send", command=self.send_chat_message)
        send_button.pack(side=tk.RIGHT, padx=5, pady=5)

        # ---- Add volume slider and mute button below the chat box ----
        volume_frame = tk.Frame(chat_container, bg="#FFFFFF")
        volume_frame.pack(fill=tk.X, pady=(0,5))
        vol_label = tk.Label(volume_frame, text="Volume:", font=("Segoe UI", 10), bg="#FFFFFF")
        vol_label.pack(side=tk.LEFT, padx=5)
        volume_slider = ttk.Scale(volume_frame, from_=0, to=100, orient=tk.HORIZONTAL,
                                  command=lambda val: self.set_volume(val))
        volume_slider.set(100)  # default to 100%
        volume_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        mute_button = ttk.Button(volume_frame, text="Mute", command=self.toggle_mute)
        mute_button.pack(side=tk.LEFT, padx=5)
        # ----------------------------------------------------------------

        return chat_container

    def send_chat_message(self):
        """Send a chat message via UDP broadcast and update the display."""
        message = self.chat_entry.get().strip()
        if message:
            formatted_message = f"{self.username}: {message}"
            self.append_chat_message(formatted_message)
            try:
                udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                chat_msg = f"CHAT|{self.username}|{message}"
                udp_sock.sendto(chat_msg.encode(), ('255.255.255.255', 50010))
                udp_sock.close()
            except Exception as e:
                print("Chat send error:", e)
            self.chat_entry.delete(0, tk.END)

    def append_chat_message(self, message):
        """Append a message to the chat history and update the chat text widget."""
        self.chat_history.append(message)
        if hasattr(self, 'chat_text') and self.chat_text:
            self.chat_text.config(state=tk.NORMAL)
            self.chat_text.insert(tk.END, message + "\n")
            self.chat_text.config(state=tk.DISABLED)
            self.chat_text.see(tk.END)

    def udp_chat_listener(self):
        """Listen for UDP chat messages on port 50010 and update the chat UI."""
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            udp_sock.bind(("", 50010))
        except Exception as e:
            print("UDP chat bind error:", e)
            return
        self.chat_listener_running = True
        while True:
            try:
                data, addr = udp_sock.recvfrom(4096)
                msg = data.decode()
                if msg.startswith("CHAT|"):
                    parts = msg.split("|", 2)
                    if len(parts) == 3:
                        sender, chat_message = parts[1], parts[2]
                        if sender != self.username:
                            self.root.after(0, lambda: self.append_chat_message(f"{sender}: {chat_message}"))
            except Exception as e:
                print("UDP chat listener error:", e)
                break
        self.chat_listener_running = False
        udp_sock.close()

    def broadcast_user_list(self):
        if self.room_code is None:
            return
        user_list_str = ",".join([f"{u}:{r}" for u, r in self.connected_users])
        message = "USER_LIST|" + user_list_str
        print(f"Broadcasting users: {user_list_str}")  # Debug print
        try:
            udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            udp_sock.sendto(message.encode(), ('255.255.255.255', 50009))
            udp_sock.close()
        except Exception as e:
            print("Broadcast error:", e)

    def udp_control_listener(self):
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            udp_sock.bind(("", 50009))
        except Exception as e:
            print("UDP control bind error:", e)
            return
        self.control_listener_running = True
        while True:
            try:
                data, addr = udp_sock.recvfrom(1024)
                msg = data.decode()
                if msg.startswith("USER_LIST|"):
                    user_list_str = msg[len("USER_LIST|"):]
                    print(f"Received user list: {user_list_str}")  # Debug print
                    new_list = []
                    for item in user_list_str.split(","):
                        if ':' in item:
                            u, r = item.split(":", 1)
                            new_list.append((u, r))
                    self.connected_users = new_list
                    self.root.after(0, self.update_client_users_view)
            except Exception as e:
                print("UDP control error:", e)
                break
        self.control_listener_running = False
        udp_sock.close()

    def show_notification(self, message):
        """Display a temporary notification in the content area."""
        notif = tk.Label(self.content_frame, text=message, font=("Segoe UI", 14), bg="#FFF176")
        notif.place(relx=0.5, rely=0.1, anchor="center")
        self.root.after(3000, notif.destroy)

    def connect_to_room(self):
        """Display a form for entering a room code to join as a client."""
        self.clear_content()
        connect_frame = tk.Frame(self.content_frame, bg="#FFFFFF")
        connect_frame.pack(expand=True)
        ttk.Label(connect_frame, text="Enter the 24-character Room Code:", style="Header.TLabel").pack(pady=10)
        room_code_entry = ttk.Entry(connect_frame, width=30)
        room_code_entry.pack(pady=5)
        error_label = ttk.Label(connect_frame, text="", foreground="red")
        error_label.pack(pady=5)

        def submit_room_code():
            code = room_code_entry.get().strip()
            if len(code) != 24:
                error_label.config(text="Invalid room code.")
            else:
                threading.Thread(target=self.attempt_connection, args=(code,), daemon=True).start()

        ttk.Button(connect_frame, text="Connect", command=submit_room_code).pack(pady=10)

    def attempt_connection(self, room_code):
        """Client attempts to discover the host and establish a TCP connection."""
        host_ip = self.discover_host(room_code, self.username)
        if host_ip is None:
            self.show_notification("No room found with that code on the local network.")
            return
        PORT = 50007
        try:
            client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_sock.connect((host_ip, PORT))
            request_message = f"REQUEST|{self.username}|{room_code}"
            client_sock.sendall(request_message.encode())
            response = client_sock.recv(1024).decode()
            if response.startswith("ACCEPT"):
                parts = response.split("|")
                if len(parts) >= 3:
                    self.host_username = parts[1]
                    user_list_str = parts[2]
                    new_list = []
                    for item in user_list_str.split(","):
                        if ':' in item:
                            u, r = item.split(":", 1)
                            new_list.append((u, r))
                    self.connected_users = new_list
                self.show_notification("Connection accepted by host. Starting audio communication.")
                self.current_client_sock = client_sock
                self.is_host = False
                self.add_room_tab()
                self.start_audio_communication(client_sock, role="client", peer_name=self.host_username)
            else:
                self.show_notification("Connection declined by host.")
                client_sock.close()
        except Exception as e:
            self.show_notification(f"Failed to connect: {e}")

    def start_server(self):
        """Host's TCP server for incoming connections."""
        HOST = ''
        PORT = 50007
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.server_socket.bind((HOST, PORT))
            self.server_socket.listen(5)
        except Exception as e:
            print(f"Server Error: {e}")
            return
        while True:
            try:
                client_sock, addr = self.server_socket.accept()
            except Exception:
                break
            threading.Thread(target=self.handle_client, args=(client_sock,), daemon=True).start()

    def udp_discovery_listener(self):
        """Host listens for UDP broadcasts for discovery on port 50008."""
        UDP_PORT = 50008
        udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            udp_sock.bind(("", UDP_PORT))
        except Exception as e:
            print(f"UDP Listener error: {e}")
            return
        while self.room_code:
            try:
                data, addr = udp_sock.recvfrom(1024)
            except Exception:
                break
            try:
                message = data.decode()
                parts = message.split('|')
                if len(parts) == 3 and parts[0] == "DISCOVER":
                    requested_code = parts[1]
                    if requested_code == self.room_code:
                        udp_sock.sendto("ROOM_FOUND".encode(), addr)
            except Exception:
                continue
        udp_sock.close()

    def discover_host(self, room_code, username):
        """Client broadcasts a UDP discovery message; returns the host IP if found."""
        UDP_PORT = 50008
        try:
            udp_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            udp_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            udp_sock.settimeout(3)
            message = f"DISCOVER|{room_code}|{username}"
            udp_sock.sendto(message.encode(), ('255.255.255.255', UDP_PORT))
            data, addr = udp_sock.recvfrom(1024)
            if data.decode() == "ROOM_FOUND":
                return addr[0]
        except Exception:
            return None
        finally:
            udp_sock.close()
        return None

    def handle_client(self, client_sock):
        """
        Host handles an incoming connection request.
        Displays an in-content prompt for Accept/Decline.
        """
        try:
            request = client_sock.recv(1024).decode()
            parts = request.split('|')
            if len(parts) != 3 or parts[0] != "REQUEST":
                client_sock.sendall("DECLINE".encode())
                client_sock.close()
                return
            client_username = parts[1]
            client_room_code = parts[2].strip()
            if client_room_code != self.room_code:
                client_sock.sendall("DECLINE".encode())
                client_sock.close()
                return

            decision_event = threading.Event()
            decision_result = {}

            def on_accept():
                decision_result['decision'] = True
                decision_event.set()
                prompt_frame.destroy()

            def on_decline():
                decision_result['decision'] = False
                decision_event.set()
                prompt_frame.destroy()

            def show_prompt():
                nonlocal prompt_frame
                prompt_frame = tk.Frame(self.content_frame, borderwidth=2, relief="flat", bg="#E8EAF6")
                prompt_frame.place(relx=0.5, rely=0.5, anchor="center")
                ttk.Label(prompt_frame, text=f"User '{client_username}' is requesting to join.", style="Header.TLabel").pack(padx=10, pady=10)
                btn_frame = tk.Frame(prompt_frame, bg="#E8EAF6")
                btn_frame.pack(pady=5)
                ttk.Button(btn_frame, text="Accept", command=on_accept).pack(side=tk.LEFT, padx=5)
                ttk.Button(btn_frame, text="Decline", command=on_decline).pack(side=tk.LEFT, padx=5)

            prompt_frame = None
            self.root.after(0, show_prompt)
            decision_event.wait()
            if decision_result.get('decision'):
                self.connected_users.append((client_username, "client"))
                self.broadcast_user_list()
                accept_msg = f"ACCEPT|{self.username}|{','.join([f'{u}:{r}' for u, r in self.connected_users])}"
                client_sock.sendall(accept_msg.encode("utf-8"))
                self.client_sockets[client_username] = client_sock
                self.root.after(0, self.update_room_view)
                self.start_audio_communication(client_sock, role="host", peer_name=client_username)
            else:
                client_sock.sendall("DECLINE".encode())
                client_sock.close()
        except Exception:
            client_sock.close()

    def start_audio_communication(self, sock, role, peer_name=None):
        """
        Begin bi-directional audio streaming over the given socket.
        For a client, the call UI is integrated into the main window.
        """
        if role == "client":
            self.show_client_call_view()

        def send_audio():
            try:
                stream = self.py_audio.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                                            input=True, frames_per_buffer=CHUNK,
                                            input_device_index=self.input_device)
            except Exception as e:
                print(f"Audio input error: {e}")
                return
            while True:
                try:
                    data = stream.read(CHUNK)
                    sock.sendall(data)
                except Exception:
                    break
            stream.stop_stream()
            stream.close()

        def receive_audio():
            try:
                stream = self.py_audio.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                                            output=True, frames_per_buffer=CHUNK,
                                            output_device_index=self.output_device)
            except Exception as e:
                print(f"Audio output error: {e}")
                return
            while True:
                try:
                    data = sock.recv(CHUNK)
                    if role == "client" and data == b"HOST_ENDED":
                        self.host_ended_call(peer_name, self.content_frame)
                        break
                    if not data:
                        if role == "host":
                            self.client_disconnected(peer_name)
                        elif role == "client":
                            self.host_ended_call(peer_name, self.content_frame)
                        break
                    # Apply volume control: if muted, output silence;
                    # otherwise, scale audio by self.volume_factor if not 1.0.
                    if self.muted:
                        data = b'\x00' * len(data)
                    elif self.volume_factor != 1.0:
                        data = self.scale_audio(data, self.volume_factor)
                    rms = get_volume(data)
                    color = volume_to_color(rms)
                    if role == "host" and peer_name:
                        self.root.after(0, lambda: self.safe_update_itemconfig(*self.indicator_widgets.get(peer_name, (None, None)), color))
                    elif role == "client":
                        self.root.after(0, lambda: self.safe_update_itemconfig(*self.call_indicator, color))
                    stream.write(data)
                except Exception:
                    if role == "host":
                        self.client_disconnected(peer_name)
                    elif role == "client":
                        self.host_ended_call(peer_name, self.content_frame)
                    break
            stream.stop_stream()
            stream.close()

        threading.Thread(target=send_audio, daemon=True).start()
        threading.Thread(target=receive_audio, daemon=True).start()

    def update_indicator(self, peer_name, color):
        """Update the volume indicator for a given user in the host room view."""
        if peer_name in self.indicator_widgets:
            canvas, oval = self.indicator_widgets[peer_name]
            self.root.after(0, lambda: self.safe_update_itemconfig(canvas, oval, color))

    def update_call_window_indicator(self, color):
        """Update the volume indicator in the client call view."""
        if self.call_indicator:
            canvas, oval = self.call_indicator
            self.root.after(0, lambda: self.safe_update_itemconfig(canvas, oval, color))

    def client_disconnected(self, peer_name):
        self.connected_users = [entry for entry in self.connected_users if entry[0] != peer_name]
        if peer_name in self.client_sockets:
            try:
                self.client_sockets[peer_name].close()
            except Exception:
                pass
            del self.client_sockets[peer_name]
        self.root.after(0, self.update_room_view)
        self.broadcast_user_list()
        self.root.after(0, lambda: self.show_notification(f"User '{peer_name}' left the call."))

    def host_ended_call(self, host_name, call_area):
        """For clients: notify when the host ends the call, then return home."""
        def notify_and_return():
            notif = tk.Label(call_area, text=f"Host {host_name} Ended The Call", font=("Segoe UI", 14), bg="#FFF176")
            notif.pack(pady=10)
            call_area.update()
            time.sleep(3)
            self.root.after(0, self.show_home)
            self.remove_room_tab()
        threading.Thread(target=notify_and_return, daemon=True).start()

    def end_call(self, sock, call_area, role):
        """Terminate the call.
        
        For clients, the room state remains so they can return via the 'Room' button.
        """
        try:
            sock.close()
        except Exception:
            pass
        self.clear_content()
        if role == "client":
            self.show_notification("Call ended.")
            self.show_home()
        elif role == "host":
            self.show_home()
            self.remove_room_tab()

    def close_room(self):
        """
        Host ends the room.
        All connected clients are notified.
        Resets the room state.
        """
        for client, sock in list(self.client_sockets.items()):
            try:
                sock.sendall(b"HOST_ENDED")
                sock.close()
            except Exception:
                pass
            del self.client_sockets[client]
        if hasattr(self, 'server_socket') and self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
        self.room_code = None
        self.connected_users = []
        self.indicator_widgets = {}
        self.remove_room_tab()
        self.show_home()

    def get_audio_devices(self, input=True):
        """Return a list of available audio devices formatted as 'index: device name'."""
        devices = []
        for i in range(self.py_audio.get_device_count()):
            info = self.py_audio.get_device_info_by_index(i)
            if input and info.get('maxInputChannels') > 0:
                devices.append(f"{i}: {info.get('name')}")
            elif not input and info.get('maxOutputChannels') > 0:
                devices.append(f"{i}: {info.get('name')}")
        return devices

    def exit_app(self):
        """Clean up and exit the application."""
        if hasattr(self, 'server_socket') and self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
        self.py_audio.terminate()
        self.root.destroy()
        sys.exit()

if __name__ == "__main__":
    root = tk.Tk()
    app = VoIPApp(root)
    root.mainloop()
