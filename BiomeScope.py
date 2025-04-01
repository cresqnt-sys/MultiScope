import json, requests, time, os, threading, re, webbrowser, random, keyboard, pyautogui, pytesseract, autoit, psutil, locale
import traceback
import pygetwindow as gw
import tkinter as tk
import ctypes
import sys

# Fix for taskbar icon - set AppUserModelID
if hasattr(sys, 'frozen'):  # Running as compiled
    myappid = 'BiomeScope.App.1.0.1.Beta'
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)

try:

    from antiafk import AntiAFK
    has_antiafk = True
except ImportError:

    has_antiafk = False
    print("AntiAFK module not available. Anti-AFK tab will be disabled.")

from tkinter import messagebox, filedialog
from PIL import Image, ImageTk
from datetime import datetime, timedelta

import ttkbootstrap as ttk

class SnippingWidget:
    def __init__(self, root, config_key=None, callback=None):
        self.root = root
        self.config_key = config_key
        self.callback = callback
        self.snipping_window = None
        self.begin_x = None
        self.begin_y = None
        self.end_x = None
        self.end_y = None

    def start(self):
        self.snipping_window = ttk.Toplevel(self.root)
        self.snipping_window.attributes('-fullscreen', True)
        self.snipping_window.attributes('-alpha', 0.3)
        self.snipping_window.configure(bg="lightblue")

        self.snipping_window.bind("<Button-1>", self.on_mouse_press)
        self.snipping_window.bind("<B1-Motion>", self.on_mouse_drag)
        self.snipping_window.bind("<ButtonRelease-1>", self.on_mouse_release)

        self.canvas = ttk.Canvas(self.snipping_window, bg="lightblue", highlightthickness=0)
        self.canvas.pack(fill=ttk.BOTH, expand=True)

    def on_mouse_press(self, event):
        self.begin_x = event.x
        self.begin_y = event.y
        self.canvas.delete("selection_rect")

    def on_mouse_drag(self, event):
        self.end_x, self.end_y = event.x, event.y
        self.canvas.delete("selection_rect")
        self.canvas.create_rectangle(self.begin_x, self.begin_y, self.end_x, self.end_y,
                                      outline="white", width=2, tag="selection_rect")

    def on_mouse_release(self, event):
        self.end_x = event.x
        self.end_y = event.y

        x1, y1 = min(self.begin_x, self.end_x), min(self.begin_y, self.end_y)
        x2, y2 = max(self.begin_x, self.end_x), max(self.begin_y, self.end_y)

        self.capture_region(x1, y1, x2, y2)
        self.snipping_window.destroy()

    def capture_region(self, x1, y1, x2, y2):
        if self.config_key:
            region = [x1, y1, x2 - x1, y2 - y1]
            print(f"Region for '{self.config_key}' set to {region}")

            if self.callback:
                self.callback(region)

class BiomePresence():
    def __init__(self):
        try:
            locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
        except locale.Error:
            locale.setlocale(locale.LC_ALL, '')

        self.version = "1.0.1-Beta"

        self.logs_dir = os.path.join(os.getenv('LOCALAPPDATA'), 'Roblox', 'logs')

        self.biome_data = self.load_biome_data()
        self.config = self.load_config()
        self.auras_data = self.load_auras_json()

        if "enable_aura_detection" not in self.config:
            self.config["enable_aura_detection"] = False

        self.accounts = self.config.get("accounts", [])

        self.verified_log_files = {}

        self.last_webhook_time = 0
        self.webhook_rate_limit = 1.0  

        print(f"Loaded {len(self.accounts)} accounts from config")
        for i, account in enumerate(self.accounts):
            username = account.get("username", "Unknown")
            ps_link = account.get("ps_link", "None")
            print(f"Account {i+1}: {username}, PS Link: {ps_link}")

        self.account_biomes = {}
        self.account_last_positions = {}
        self.account_last_sent = {}

        for account in self.accounts:
            account_name = account.get("username", "")
            if account_name:
                self.account_biomes[account_name] = None
                self.account_last_positions[account_name] = 0
                self.account_last_sent[account_name] = {biome: datetime.min for biome in self.biome_data}

        self.current_biome = None
        self.last_sent = {biome: datetime.min for biome in self.biome_data}

        self.biome_counts = self.config.get("biome_counts", {})
        for biome in self.biome_data.keys():
            if biome not in self.biome_counts:
                self.biome_counts[biome] = 0

        self.start_time = None
        self.saved_session = self.parse_session_time(self.config.get("session_time", "0:00:00"))

        self.last_position = 0
        self.detection_running = False
        self.detection_thread = None
        self.lock = threading.Lock()
        self.logs = self.load_logs()

        self.last_br_time = datetime.min
        self.last_sc_time = datetime.min
        self.last_mt_time = datetime.min
        self.on_auto_merchant_state = False

        self.auto_pop_state = False
        self.buff_vars = {}
        self.buff_amount_vars = {}

        self.reconnecting_state = False

        self.variables = {}
        self.init_gui()

        self.last_aura_found = None

    def parse_session_time(self, session_time_str):
        """Parse session time from string format to seconds"""
        try:
            h, m, s = session_time_str.split(':')
            return int(h) * 3600 + int(m) * 60 + int(s)
        except (ValueError, AttributeError):
            return 0

    def append_log(self, message):
        """Add a message to the logs list and display it"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        log_entry = f"[{timestamp}] {message}"

        if not hasattr(self, 'logs'):
            self.logs = []

        self.logs.append(log_entry)

        if hasattr(self, 'logs_text') and self.logs_text:
            try:
                self.display_logs()
            except Exception:
                pass  

        print(log_entry)

    def load_logs(self):
        """Load logs from previous sessions"""
        if os.path.exists('macro_logs.txt'):
            with open('macro_logs.txt', 'r') as file:
                lines = file.read().splitlines()
                return lines
        return []

    def load_biome_data(self):
        biomes_paths = [
            "biomes_data.json",
            "source_code/biomes_data.json",
            os.path.join(os.path.dirname(__file__), "biomes_data.json"),
            os.path.join(os.path.dirname(__file__), "source_code/biomes_data.json")
        ]

        default_biome_data = {
            "WINDY": {
                "color": "0x9ae5ff",
                "thumbnail_url": "https://i.postimg.cc/6qPH4wy6/image.png"
            },
            "RAINY": {
                "color": "0x027cbd",
                "thumbnail_url": "https://static.wikia.nocookie.net/sol-rng/images/e/ec/Rainy.png"
            },
            "SNOWY": {
                "color": "0xDceff9",
                "thumbnail_url": "https://static.wikia.nocookie.net/sol-rng/images/3/36/Snowy.png"
            },
            "SAND STORM": {
                "color": "0x8F7057",
                "thumbnail_url": "https://i.postimg.cc/3JyL25Kz/image.png"
            },
            "HELL": {
                "color": "0xff4719",
                "thumbnail_url": "https://i.postimg.cc/hGC5xNyY/image.png"
            },
            "STARFALL": {
                "color": "0x011ab7",
                "thumbnail_url": "https://i.postimg.cc/1t0dY4J8/image.png"
            },
            "CORRUPTION": {
                "color": "0x6d32a8",
                "thumbnail_url": "https://i.postimg.cc/ncZQ84Dh/image.png"
            },
            "NULL": {
                "color": "0x838383",
                "thumbnail_url": "https://static.wikia.nocookie.net/sol-rng/images/f/fc/NULLLL.png"
            },
            "GLITCHED": {
                "color": "0xbfff00",
                "thumbnail_url": "https://i.postimg.cc/W3Lhtn5g/image.png"
            },

            "DREAMSPACE": {
                "color": "0xea9dda",
                "thumbnail_url": "https://i.postimg.cc/rFjCcW3w/image.png"
            }
        }

        try:
            for path in biomes_paths:
                if os.path.exists(path):
                    with open(path, "r") as file:
                        biome_data = json.load(file)
                        return biome_data
        except Exception as e:
            print(f"Error loading biomes_data.json: {e}")
            self.error_logging(e, f"Error loading biomes_data.json")

        with open("biomes_data.json", "w") as file:
            json.dump(default_biome_data, file, indent=4)
            print("Default biomes_data.json created.")

        return default_biome_data

    def load_auras_json(self):
        """Load auras data from JSON - Simplified for core version"""
        return {}

    def error_logging(self, exception, custom_message=None, max_log_size=3 * 1024 * 1024):
        log_file = "error_logs.txt"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        error_type = type(exception).__name__
        error_message = str(exception)
        stack_trace = traceback.format_exc()

        if not os.path.exists(log_file):
            with open(log_file, "w") as log:
                log.write("Error Log File Created\n")
                log.write("-" * 40 + "\n")

        if os.path.exists(log_file) and os.path.getsize(log_file) > max_log_size:
            with open(log_file, "r") as log:
                lines = log.readlines()
            with open(log_file, "w") as log:
                log.writelines(lines[-1000:])

        with open(log_file, "a") as log:
            log.write(f"\n[{timestamp}] ERROR LOG\n")
            log.write(f"Error Type: {error_type}\n")
            log.write(f"Error Message: {error_message}\n")
            if custom_message:
                log.write(f"Custom Message: {custom_message}\n")
            log.write(f"Traceback:\n{stack_trace}\n")
            log.write("-" * 40 + "\n")

        print(f"Error logged to {log_file}.")

    def save_logs(self):
        log_file_path = 'macro_logs.txt'

        if os.path.exists(log_file_path) and os.path.getsize(log_file_path) > 2 * 1024 * 1024:
            with open(log_file_path, 'w') as file:
                file.write("")
        else:
            with open(log_file_path, 'a') as file:
                for log in self.logs:
                    file.write(log + "\n")

    def save_config(self):
        """Save configuration to file - simplified version"""
        try:
            with open("config.json", "r") as file:
                config = json.load(file)
        except FileNotFoundError:
            config = {}

        session_time = self.get_total_session_time()

        if hasattr(self, 'webhook_entries'):
            webhooks = []
            for entry in self.webhook_entries:
                url = entry.get().strip()
                if url:  
                    webhooks.append({"url": url, "user_id": ""})
            config["webhooks"] = webhooks

        if hasattr(self, 'variables'):
            biome_notifier = {}
            for biome, var in self.variables.items():
                biome_notifier[biome] = var.get()
            config["biome_notifier"] = biome_notifier

        if 'antiafk_first_launch_shown' in self.config:
            config['antiafk_first_launch_shown'] = self.config['antiafk_first_launch_shown']

        config.update({
            "biome_counts": self.biome_counts,
            "session_time": session_time,
            "accounts": self.accounts
        })

        with open("config.json", "w") as file:
            json.dump(config, file, indent=4)

        try:
            with open("config.json", "r") as file:
                saved_config = json.load(file)
        except Exception as e:
            print(f"Error verifying config file: {str(e)}")

        self.config = config

    def load_config(self):
        try:
            config_paths = [
                "config.json",
                "source_code/config.json",
                os.path.join(os.path.dirname(__file__), "config.json"),
                os.path.join(os.path.dirname(__file__), "source_code/config.json")
            ]

            for path in config_paths:
                if os.path.exists(path):
                    with open(path, "r") as file:
                        config = json.load(file)
                        return config

            return {"biome_counts": {biome: 0 for biome in self.biome_data}, "session_time": "0:00:00"}
        except Exception as e:
            self.error_logging(e, "Error at loading config.json. Try adding empty: '{}' into config.json to fix this error!")
            return {"biome_counts": {biome: 0 for biome in self.biome_data}, "session_time": "0:00:00"}

    def import_config(self):
        try:
            file_path = filedialog.askopenfilename(
                defaultextension=".json",
                filetypes=[("JSON files", "*.json")],
                title="Select CONFIG.JSON please!"
            )

            if not file_path: return
            with open(file_path, "r") as file: config = json.load(file)
            self.config = config

            self.webhook_url_entry.delete(0, 'end')
            self.webhook_url_entry.insert(0, config.get("webhook_url", ""))
            self.private_server_link_entry.delete(0, 'end')
            self.private_server_link_entry.insert(0, config.get("private_server_link", ""))

            self.auto_pop_glitched_var.set(config.get("auto_pop_glitched", False))
            self.record_rarest_biome_var.set(config.get("record_rare_biome", False))
            self.rarest_biome_keybind_var.set(config.get("rare_biome_record_keybind", "shift + F8"))
            self.br_var.set(config.get("biome_randomizer", False))
            self.br_duration_var.set(config.get("br_duration", "30"))
            self.sc_var.set(config.get("strange_controller", False))
            self.sc_duration_var.set(config.get("sc_duration", "15"))
            self.mt_var.set(config.get("merchant_teleporter", False))
            self.mt_duration_var.set(config.get("mt_duration", "1"))
            self.auto_reconnect_var.set(config.get("auto_reconnect", False))
            self.click_delay_var.set(config.get("inventory_click_delay", "0"))

            self.enable_aura_detection_var.set(config.get("enable_aura_detection", False))
            self.aura_user_id_var.set(config.get("aura_user_id", ""))
            self.ping_minimum_var.set(config.get("ping_minimum", "100000"))
            self.enable_aura_record_var.set(config.get("enable_aura_record", False))
            self.aura_record_keybind_var.set(config.get("aura_record_keybind", "shift + F8"))
            self.aura_record_minimum_var.set(config.get("aura_record_minimum", "500000"))

            self.merchant_extra_slot_var.set(config.get("merchant_extra_slot", "0"))
            self.ping_mari_var.set(config.get("ping_mari", False))
            self.mari_user_id_var.set(config.get("mari_user_id", ""))
            self.ping_jester_var.set(config.get("ping_jester", False))
            self.jester_user_id_var.set(config.get("jester_user_id", ""))

            self.biome_counts = config.get("biome_counts", {biome: 0 for biome in self.biome_data})
            for biome, count in self.biome_counts.items():
                if biome in self.stats_labels:
                    self.stats_labels[biome].config(text=f"{biome}: {count}")

            total_biomes = sum(self.biome_counts.values())
            self.total_biomes_label.config(text=f"Total Biomes Found: {total_biomes}")

            session_time = config.get("session_time")
            self.session_label.config(text=f"Running Session: {session_time}")
            self.save_config()
            messagebox.askokcancel("Ok imported!!", "Your selected config.json imported and saved successfully!")
        except Exception as e:
            self.error_logging(e, "Error at importing config.json")

    def init_gui(self):
        """Initialize GUI elements"""
        selected_theme = self.config.get("selected_theme", "darkly")
        self.root = ttk.Window(themename=selected_theme)
        
        # Set window icon explicitly
        if hasattr(sys, '_MEIPASS'):
            # Running as compiled exe
            bundle_dir = sys._MEIPASS
            icon_path = os.path.join(bundle_dir, 'biomescope.ico')
        else:
            # Running as script
            icon_path = 'biomescope.ico'
            
        if os.path.exists(icon_path):
            self.root.iconbitmap(icon_path)
            
        self.root.title(f"BiomeScope | Version {self.version}")
        self.root.geometry("695x450")  
        self.root.resizable(False, False)  
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self.variables = {biome: ttk.StringVar(master=self.root, value=self.config.get("biome_notifier", {}).get(biome, "Message"))
                        for biome in self.biome_data}

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=5, pady=5)

        webhook_frame = ttk.Frame(self.notebook)
        credits_frame = ttk.Frame(self.notebook)
        stats_frame = ttk.Frame(self.notebook)

        self.notebook.add(webhook_frame, text='Webhook')
        self.notebook.add(stats_frame, text='Stats')

        if has_antiafk:
            self.antiafk = AntiAFK(self, self.config)

            self.antiafk.create_tab(self.notebook)

        self.notebook.add(credits_frame, text='Credits')

        self.create_webhook_tab(webhook_frame)
        self.create_stats_tab(stats_frame)
        self.create_credit_tab(credits_frame)

        button_frame = ttk.Frame(self.root)
        button_frame.pack(pady=5, padx=5, fill='x')

        left_buttons = ttk.Frame(button_frame)
        left_buttons.pack(side='left')

        self.status_frame = ttk.Frame(self.root)
        self.status_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=5)

        self.status_label = ttk.Label(self.status_frame, text="Ready")
        self.status_label.pack(side=tk.LEFT)

        self.version_label = ttk.Label(self.status_frame, text=f"v{self.version}")
        self.version_label.pack(side=tk.RIGHT)

        keyboard.add_hotkey('F1', self.start_detection)
        keyboard.add_hotkey('F2', self.stop_detection)

        self.check_for_updates()
        self.root.mainloop()

    def create_activity_tab(self, parent):
        """Create the activity tracking tab"""
        try:

            self.activity_controls = ttk.LabelFrame(parent, text="Activity Controls")
            self.activity_controls.pack(fill=tk.X, padx=10, pady=10)

            self.activity_username_frame = ttk.Frame(self.activity_controls)
            self.activity_username_frame.pack(fill=tk.X, padx=10, pady=10)

            ttk.Label(self.activity_username_frame, text="Username:").pack(side=tk.LEFT, padx=(0, 5))
            self.username_var = tk.StringVar()
            self.activity_username_entry = ttk.Entry(self.activity_username_frame, textvariable=self.username_var, width=20)
            self.activity_username_entry.pack(side=tk.LEFT, padx=(0, 10))

            self.view_activity_button = ttk.Button(
                self.activity_username_frame, 
                text="View Activity", 
                command=self.display_user_activity
            )
            self.view_activity_button.pack(side=tk.LEFT, padx=5)

            ttk.Label(self.activity_username_frame, text="Days:").pack(side=tk.LEFT, padx=(10, 5))
            self.days_back_var = tk.StringVar(value="30")
            self.days_back_combo = ttk.Combobox(
                self.activity_username_frame, 
                textvariable=self.days_back_var,
                values=["7", "14", "30", "60", "90"],
                width=5
            )
            self.days_back_combo.pack(side=tk.LEFT, padx=5)

            self.log_files_frame = ttk.LabelFrame(parent, text="Log Files")
            self.log_files_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

            self.log_files_tree = ttk.Treeview(self.log_files_frame, columns=("Filename", "Size", "Last Modified"), show="headings")
            self.log_files_tree.heading("Filename", text="Filename")
            self.log_files_tree.heading("Size", text="Size")
            self.log_files_tree.heading("Last Modified", text="Last Modified")

            self.log_files_tree.column("Filename", width=200)
            self.log_files_tree.column("Size", width=100)
            self.log_files_tree.column("Last Modified", width=150)

            self.log_files_scrollbar = ttk.Scrollbar(self.log_files_frame, orient="vertical", command=self.log_files_tree.yview)
            self.log_files_tree.configure(yscrollcommand=self.log_files_scrollbar.set)

            self.log_files_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            self.log_files_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

            self.refresh_logs_button = ttk.Button(
                self.log_files_frame, 
                text="Refresh Log Files", 
                command=self.refresh_log_files
            )
            self.refresh_logs_button.pack(side=tk.BOTTOM, pady=5)

            self.refresh_log_files()

        except Exception as e:
            self.error_logging(e, "Error creating activity tab")

    def update_theme(self, theme_name):
        self.root.style.theme_use(theme_name)
        self.config["selected_theme"] = theme_name
        self.save_config()

    def check_for_updates(self):

        current_version = self.version
        dont_ask_again = self.config.get("dont_ask_for_update", False)

        if dont_ask_again:
            return

        try:
            response = requests.get("https://api.github.com/repos/cresqnt-sys/BiomeScope/releases/latest")

            if response.status_code == 404:
                print("No releases found or repository not accessible")
                return

            response.raise_for_status()
            latest_release = response.json()

            latest_version = latest_release['tag_name']
            if latest_version.startswith('v'):
                latest_version = latest_version[1:]

            if latest_version != current_version:
                message = f"New update of BiomeScope {latest_version} is available. Do you want to download the newest version?"
                if messagebox.askyesno("Update Available!!", message):

                    if latest_release['assets'] and len(latest_release['assets']) > 0:
                        download_url = latest_release['assets'][0]['browser_download_url']
                        self.download_update(download_url)
                    else:

                        messagebox.showinfo("No Download Available", 
                                           f"No downloadable assets found for version {latest_version}. Please visit the GitHub repository to download manually.")
                else:
                    if messagebox.askyesno("Don't Ask Again", "Would you like to stop receiving update notifications?"):
                        self.config["dont_ask_for_update"] = True
                        self.save_config()

        except requests.RequestException as e:
            print(f"Update check skipped: {e}")

            return

    def download_update(self, download_url):
        try:
            zip_filename = os.path.basename(download_url)
            save_path = filedialog.asksaveasfilename(defaultextension=".zip", initialfile=zip_filename, title="Save As")

            if not save_path: 
                return

            self.append_log(f"Downloading update from {download_url}...")

            response = requests.get(download_url)
            response.raise_for_status()

            with open(save_path, 'wb') as file:
                file.write(response.content)

            messagebox.showinfo("Download Complete", f"The latest version has been downloaded as {save_path}. Make sure to turn off antivirus and extract it manually.")
            self.append_log(f"Update downloaded successfully to {save_path}")
        except requests.RequestException as e:
            error_msg = f"Failed to download the update: {e}"
            print(error_msg)
            self.append_log(error_msg)
            messagebox.showerror("Download Failed", f"Failed to download the update: {e}")
        except Exception as e:
            error_msg = f"Error during update download: {e}"
            print(error_msg)
            self.append_log(error_msg)
            self.error_logging(e, "Error during update download")
            messagebox.showerror("Download Error", f"An error occurred during download: {e}")

    def open_biome_settings(self):
        settings_window = ttk.Toplevel(self.root)
        settings_window.title("Biome Settings")

        silly_note_label = ttk.Label(settings_window, text="GLITCHED and DREAMSPACE are both forced 'everyone' ping grrr >:((", foreground="red")
        silly_note_label.grid(row=0, columnspan=2, padx=(10, 0), pady=(10, 0))

        biomes = [biome for biome in self.biome_data.keys() if biome not in ["GLITCHED", "DREAMSPACE"]]
        window_height = max(475, len(biomes) * 43)
        settings_window.geometry(f"465x{window_height}")

        options = ["None", "Message"]

        for i, biome in enumerate(biomes):
            ttk.Label(settings_window, text=f"{biome}:").grid(row=i + 1, column=0, sticky="e")

            if biome not in self.variables:
                self.variables[biome] = ttk.StringVar(value="Message")

            dropdown = ttk.Combobox(settings_window, textvariable=self.variables[biome], values=options, state="readonly")
            dropdown.grid(row=i + 1, column=1, pady=5)

        def save_biome_setting():
            self.save_config()
            settings_window.destroy()

        ttk.Button(settings_window, text="Save", command=save_biome_setting).grid(row=len(biomes) + 2, column=1, pady=10)

    def open_buff_selections_window(self):
        pass

    def create_webhook_tab(self, frame):

        webhook_frame = ttk.Frame(frame)
        webhook_frame.pack(fill='both', expand=True, padx=5, pady=5)

        webhook_label = ttk.Label(webhook_frame, text="Discord Webhooks")
        webhook_label.pack(anchor='w', padx=5, pady=(5, 0))

        help_text = ttk.Label(webhook_frame, 
                              text="Add Discord webhook URLs to receive notifications about biomes, auras, and merchants.",
                              wraplength=650)
        help_text.pack(fill='x', padx=5, pady=(0, 5))

        accounts_btn_frame = ttk.Frame(webhook_frame)
        accounts_btn_frame.pack(fill='x', padx=5, pady=(0, 10))

        manage_accounts_btn = ttk.Button(
            accounts_btn_frame,
            text="Manage Accounts",
            command=self.open_accounts_manager
        )
        manage_accounts_btn.pack(side='left', padx=(0, 5))

        account_note = ttk.Label(webhook_frame,
                               text="Use the Manage Accounts button to configure private server links and multiple accounts.",
                               wraplength=650,
                               foreground="#666666",
                               font=("Arial", 9, "italic"))
        account_note.pack(fill='x', padx=5, pady=(0, 10))

        content_area = ttk.Frame(webhook_frame)
        content_area.pack(fill='both', expand=True)

        container_frame = ttk.Frame(content_area)
        container_frame.pack(fill='both', expand=True, padx=5, pady=2)

        canvas = tk.Canvas(container_frame, highlightthickness=0, 
                          bg=ttk.Style().lookup('TFrame', 'background'),
                          height=180)  

        scrollbar = ttk.Scrollbar(container_frame, orient="vertical", command=canvas.yview)

        self.webhook_content_frame = ttk.Frame(canvas)

        def update_scroll_region(event=None):
            bbox = canvas.bbox("all")
            if bbox:
                width = bbox[2] - bbox[0]
                height = bbox[3] - bbox[1]

                if height > canvas.winfo_height():
                    canvas.configure(scrollregion=bbox)
                else:

                    canvas.configure(scrollregion=(0, 0, width, canvas.winfo_height()))

        self.webhook_content_frame.bind("<Configure>", update_scroll_region)

        canvas.create_window((0, 0), window=self.webhook_content_frame, anchor="nw", width=670)
        canvas.configure(yscrollcommand=scrollbar.set)

        def _on_mousewheel(event):

            if canvas.bbox("all") and (canvas.bbox("all")[3] - canvas.bbox("all")[1]) > canvas.winfo_height():
                canvas.yview_scroll(int(-1*(event.delta/120)), "units")

        canvas.bind("<MouseWheel>", _on_mousewheel)

        frame.bind("<Unmap>", lambda e: canvas.unbind_all("<MouseWheel>"))

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.webhook_entries = []
        webhooks = self.config.get("webhooks", [{"url": "", "user_id": ""}])

        def add_webhook_entry(webhook=None):
            entry_idx = len(self.webhook_entries)

            entry_frame = ttk.Frame(self.webhook_content_frame)
            entry_frame.pack(fill='x', pady=1, padx=2)

            idx_label = ttk.Label(entry_frame, text=f"#{entry_idx + 1}", width=3)
            idx_label.pack(side='left', padx=(0, 2))

            url_entry = ttk.Entry(entry_frame)
            url_entry.pack(side='left', fill='x', expand=True, padx=2)
            if webhook:
                url_entry.insert(0, webhook.get("url", ""))
            url_entry.configure(show="•")

            status_label = ttk.Label(entry_frame, text="Empty", width=6)
            status_label.pack(side='left', padx=2)

            def toggle_visibility():
                current = url_entry.cget("show")
                url_entry.configure(show="" if current else "•")

            def remove_webhook():
                entry_frame.destroy()
                self.webhook_entries.remove(url_entry)
                self.save_config()

                for i, child in enumerate(self.webhook_content_frame.winfo_children()):
                    for idx_label in child.winfo_children():
                        if isinstance(idx_label, ttk.Label) and idx_label.cget("width") == 3:
                            idx_label.configure(text=f"#{i + 1}")
                            break

            popup = tk.Menu(self.root, tearoff=0)
            popup.add_command(label="Show/Hide URL", command=toggle_visibility)
            popup.add_command(label="Test Webhook", 
                            command=lambda: self.test_webhook(url_entry.get().strip()))
            popup.add_separator()
            popup.add_command(label="Remove Webhook", command=remove_webhook)

            def show_popup(event):
                popup.post(event.x_root, event.y_root)

            menu_btn = ttk.Button(entry_frame, text=">", width=3,
                                command=lambda e=None: None,
                                style="info.TButton")
            menu_btn.pack(side='left', padx=1)
            menu_btn.bind("<Button-1>", show_popup)

            self.webhook_entries.append(url_entry)

            def validate_webhook(event=None):
                url = url_entry.get().strip()
                if not url:
                    status_label.configure(text="Empty", foreground="gray")
                    return False

                if not url.startswith("https://discord.com/api/webhooks/"):
                    status_label.configure(text="Invalid", foreground="red")
                    return False

                try:

                    response = requests.get(url, params={"wait": "true"})

                    if response.status_code == 200:
                        status_label.configure(text="Valid", foreground="green")
                        return True
                    else:
                        status_label.configure(text="Invalid", foreground="red")
                        return False
                except Exception as e:
                    print(f"Error validating webhook: {e}")
                    status_label.configure(text="Error", foreground="red")
                    return False

            url_entry.bind("<FocusOut>", lambda event: [self.save_config(), validate_webhook()])
            validate_webhook()

        for webhook in webhooks:
            add_webhook_entry(webhook)

        add_webhook_btn = ttk.Button(content_area, text="Add Webhook", 
                                    command=lambda: add_webhook_entry(),
                                    style="info.TButton")
        add_webhook_btn.pack(anchor='w', padx=5, pady=5)

        bottom_controls = ttk.Frame(webhook_frame)
        bottom_controls.pack(side="bottom", fill="x", padx=5, pady=5)

        ttk.Button(bottom_controls, text="Configure Biomes", 
                  command=self.open_biome_settings,
                  style="info.TButton").pack(side="left", padx=2)

        ttk.Button(bottom_controls, text="Import Config", 
                  command=self.import_config,
                  style="info.TButton").pack(side="left", padx=2)

        ttk.Button(bottom_controls, text="Stop (F2)", 
                  command=self.stop_detection,
                  style="danger.TButton").pack(side="right", padx=2)

        ttk.Button(bottom_controls, text="Start (F1)", 
                  command=self.start_detection,
                  style="success.TButton").pack(side="right", padx=2)

    def create_misc_tab(self, frame):
        """Create the miscellaneous tab - Removed for simplified version"""
        pass

    def check_disconnect_loop(self):
        """Check for disconnections - Removed for simplified version"""
        pass

    def check_roblox_procs(self):
        """Check for Roblox processes - Removed for simplified version"""
        pass

    def fallback_reconnect(self, current_attempt):
        """Fallback reconnection - Removed for simplified version"""
        pass

    def terminate_roblox_processes(self):
        """Terminate Roblox processes - Removed for simplified version"""
        pass

    def Global_MouseClick(self, x, y, click=1):
        """Simulate a mouse click - Removed for simplified version"""
        pass

    def create_antiafk_tab(self, frame):
        """Create the Anti-AFK tab with controls for anti-AFK functionality"""

        info_frame = ttk.LabelFrame(frame, text="Roblox Anti-AFK")
        info_frame.pack(fill=tk.X, padx=10, pady=10)

        description = ("Anti-AFK functionality keeps your Roblox characters active even when the window isn't focused.\n"
                      "Multi-instance support allows managing multiple Roblox windows simultaneously.")
        desc_label = ttk.Label(info_frame, text=description, wraplength=650)
        desc_label.pack(anchor="w", padx=10, pady=10)

        controls_frame = ttk.Frame(info_frame)
        controls_frame.pack(fill=tk.X, padx=10, pady=5)

        self.antiafk_enabled_var = tk.BooleanVar(value=self.config.get("antiafk_enabled", False))
        self.antiafk_enabled_cb = ttk.Checkbutton(
            controls_frame, 
            text="Enable Anti-AFK", 
            variable=self.antiafk_enabled_var,
            command=self.toggle_antiafk
        )
        self.antiafk_enabled_cb.grid(row=0, column=0, sticky="w", padx=5, pady=5)

        self.multi_instance_var = tk.BooleanVar(value=self.config.get("multi_instance_enabled", False))
        self.multi_instance_cb = ttk.Checkbutton(
            controls_frame, 
            text="Enable Multi-Instance Support", 
            variable=self.multi_instance_var,
            command=self.toggle_multi_instance
        )
        self.multi_instance_cb.grid(row=0, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(controls_frame, text="Action Interval:").grid(row=1, column=0, sticky="w", padx=5, pady=5)

        self.interval_var = tk.StringVar(value=str(self.config.get("antiafk_interval", 540)))
        interval_values = ["180", "360", "540", "660", "780", "900", "1080"] 
        if self.config.get("antiafk_dev_mode", False):
            interval_values = ["5", "20"] + interval_values

        self.interval_combo = ttk.Combobox(
            controls_frame,
            textvariable=self.interval_var,
            values=interval_values,
            width=10,
            state="readonly"
        )
        self.interval_combo.grid(row=1, column=1, sticky="w", padx=5, pady=5)
        self.interval_combo.bind("<<ComboboxSelected>>", lambda e: self.update_antiafk_config())

        ttk.Label(controls_frame, text="Action Type:").grid(row=2, column=0, sticky="w", padx=5, pady=5)

        self.action_type_var = tk.StringVar(value=self.config.get("antiafk_action", "space"))
        self.action_combo = ttk.Combobox(
            controls_frame,
            textvariable=self.action_type_var,
            values=["space", "ws", "zoom"],
            width=10,
            state="readonly"
        )
        self.action_combo.grid(row=2, column=1, sticky="w", padx=5, pady=5)
        self.action_combo.bind("<<ComboboxSelected>>", lambda e: self.update_antiafk_config())

        self.user_safe_var = tk.BooleanVar(value=self.config.get("antiafk_user_safe", False))
        self.user_safe_cb = ttk.Checkbutton(
            controls_frame, 
            text="True-AFK Mode (Wait for inactivity before performing actions)", 
            variable=self.user_safe_var,
            command=self.update_antiafk_config
        )
        self.user_safe_cb.grid(row=3, column=0, columnspan=2, sticky="w", padx=5, pady=5)

        status_frame = ttk.LabelFrame(frame, text="Status")
        status_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.antiafk_status_text = tk.Text(status_frame, height=10, wrap="word", state="disabled")
        self.antiafk_status_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        scrollbar = ttk.Scrollbar(self.antiafk_status_text, orient="vertical", command=self.antiafk_status_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.antiafk_status_text.config(yscrollcommand=scrollbar.set)

        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X, padx=10, pady=10)

        self.test_antiafk_btn = ttk.Button(
            button_frame,
            text="Test Anti-AFK Action",
            command=self.test_antiafk_action,
            style="info.TButton"
        )
        self.test_antiafk_btn.pack(side=tk.LEFT, padx=5, pady=5)

        self.show_roblox_btn = ttk.Button(
            button_frame,
            text="Show Roblox",
            command=self.show_roblox_windows,
            style="success.TButton"
        )
        self.show_roblox_btn.pack(side=tk.LEFT, padx=5, pady=5)

        self.hide_roblox_btn = ttk.Button(
            button_frame,
            text="Hide Roblox",
            command=self.hide_roblox_windows,
            style="danger.TButton"
        )
        self.hide_roblox_btn.pack(side=tk.LEFT, padx=5, pady=5)

        self.stop_antiafk_btn = ttk.Button(
            button_frame,
            text="Stop Anti-AFK",
            command=lambda: self.toggle_antiafk(False),
            style="danger.TButton"
        )
        self.stop_antiafk_btn.pack(side=tk.RIGHT, padx=5, pady=5)

        self.start_antiafk_btn = ttk.Button(
            button_frame,
            text="Start Anti-AFK",
            command=lambda: self.toggle_antiafk(True),
            style="success.TButton"
        )
        self.start_antiafk_btn.pack(side=tk.RIGHT, padx=5, pady=5)

        self.update_antiafk_button_states()

        self.update_antiafk_status("Anti-AFK tab initialized. Use the buttons above to control the functionality.")

        self.initialize_antiafk_system()

    def initialize_antiafk_system(self):
        """Initialize the Anti-AFK system and handle the first launch instructions flag"""

        if 'antiafk_first_launch_shown' not in self.config:
            self.config['antiafk_first_launch_shown'] = False
            self.save_config()

    def create_stats_tab(self, frame):
        """Create the stats tab to display biome statistics"""

        self.stats_labels = {}
        biomes = list(self.biome_data.keys())

        columns = 5
        row = 0
        for i, biome in enumerate(biomes):

            try:
                color = f"#{int(self.biome_data[biome]['color'], 16):06x}"
            except:
                color = "#FFFFFF"  

            label = ttk.Label(frame, text=f"{biome}: {self.biome_counts.get(biome, 0)}", foreground=color)

            row = i // columns
            col = i % columns
            label.grid(row=row, column=col, sticky="w", padx=10, pady=5)
            self.stats_labels[biome] = label

        total_biomes = sum(self.biome_counts.values())
        self.total_biomes_label = ttk.Label(frame, text=f"Total Biomes Found: {total_biomes}", foreground="light green")
        self.total_biomes_label.grid(row=row + 1, column=0, columnspan=columns, sticky="w", padx=10, pady=10)

        session_time = self.config.get("session_time", "00:00:00")
        self.session_label = ttk.Label(frame, text=f"Running Session: {session_time}")
        self.session_label.grid(row=row + 2, column=0, columnspan=columns, sticky="w", padx=10, pady=10)

        self.update_session_timer()

        logs_frame = ttk.Frame(frame, borderwidth=2, relief="solid")
        logs_frame.grid(row=0, column=columns + 1, rowspan=row + 3, sticky="nsew", padx=10, pady=2)

        logs_label = ttk.Label(logs_frame, text="Biome Logs")
        logs_label.pack(anchor="w", padx=5, pady=2)

        search_entry = ttk.Entry(logs_frame)
        search_entry.pack(anchor="w", padx=5, pady=5, fill="x")
        search_entry.bind("<KeyRelease>", lambda event: self.filter_logs(search_entry.get()))

        self.logs_text = tk.Text(logs_frame, height=15, width=30, wrap="word")
        self.logs_text.pack(expand=True, fill="both", padx=5, pady=5)

        scrollbar = ttk.Scrollbar(logs_frame, orient="vertical", command=self.logs_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.logs_text.config(yscrollcommand=scrollbar.set)

        self.display_logs()

    def update_session_timer(self):
        """Update the session timer every second"""
        if hasattr(self, 'detection_running') and self.detection_running:
            session_time = self.get_total_session_time()
            if hasattr(self, 'session_label'):
                self.session_label.config(text=f"Running Session: {session_time}")

        if hasattr(self, 'root'):
            self.root.after(1000, self.update_session_timer)

    def get_total_session_time(self):
        """Get the total session time in HH:MM:SS format"""
        try:
            if hasattr(self, 'start_time') and self.start_time:
                elapsed_time = datetime.now() - self.start_time
                total_seconds = int(elapsed_time.total_seconds()) + self.saved_session
            else:
                total_seconds = self.saved_session

            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)

            return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        except Exception as e:
            print(f"Error in get_total_session_time: {e}")
            return "00:00:00"

    def filter_logs(self, keyword):
        """Filter logs based on keyword"""
        if not hasattr(self, 'logs'):
            return

        filtered_logs = [log for log in self.logs if keyword.lower() in log.lower()]
        self.display_logs(filtered_logs)

    def display_logs(self, logs=None):
        """Display logs in the text widget"""
        if not hasattr(self, 'logs_text'):
            return

        self.logs_text.config(state="normal")
        self.logs_text.delete(1.0, "end")

        if logs is None and hasattr(self, 'logs'):
            logs = self.logs
        else:
            logs = logs or []

        last_logs = logs[-30:] if len(logs) > 30 else logs

        for log in last_logs: 
            self.logs_text.insert("end", log + "\n")

        self.logs_text.config(state="disabled")
        self.logs_text.see("end")  

    def create_credit_tab(self, frame):
        """Create the credits tab with information about the application"""

        title_label = ttk.Label(frame, text="BiomeScope", font=("Arial", 16, "bold"))
        title_label.pack(pady=(20, 5))

        version_label = ttk.Label(frame, text=f"Version {self.version}")
        version_label.pack(pady=5)

        desc_label = ttk.Label(frame, text="Just another Sols RNG Biome Tracker.", wraplength=400)
        desc_label.pack(pady=10)

        credits_frame = ttk.LabelFrame(frame, text="Credits")
        credits_frame.pack(fill="x", padx=20, pady=10)

        creator_label = ttk.Label(credits_frame, text="Created by: cresqnt_", font=("Arial", 10, "bold"))
        creator_label.pack(anchor="w", padx=10, pady=5)

        contribs_label = ttk.Label(credits_frame, text="Contributors:", font=("Arial", 10, "bold"))
        contribs_label.pack(anchor="w", padx=10, pady=(10, 0))

        contributors = [
            "Noteab (Original Creator)",
            "Bor Man (Inspiration for multi account)",
            "Maxsteller (Original Inspiration)"
        ]
        for contributor in contributors:
            contrib_item = ttk.Label(credits_frame, text=f"• {contributor}")
            contrib_item.pack(anchor="w", padx=30, pady=2)

        support_frame = ttk.LabelFrame(frame, text="Support")
        support_frame.pack(fill="x", padx=20, pady=10)

        discord_label = ttk.Label(support_frame, text="Discord Server: Soon")
        discord_label.pack(anchor="w", padx=10, pady=5)

        github_label = ttk.Label(support_frame, text="GitHub: https://github.com/cresqnt/BiomeScope")
        github_label.pack(anchor="w", padx=10, pady=5)

        copyright_label = ttk.Label(frame, text="© 2023-2024 Noteab. All rights reserved.")
        copyright_label.pack(side="bottom", pady=20)

    def create_merchant_tab(self, frame):
        pass

    def check_tesseract_ocr(self):
        pass

    def download_tesseract(self):
        pass

    def open_merchant_calibration_window(self):
        pass

    def merchant_snipping(self, config_key):
        pass

    def save_merchant_coordinates(self, calibration_window):
        pass

    def open_mari_settings(self):
        pass

    def save_mari_selections(self, mari_window):
        pass

    def open_jester_settings(self):
        pass

    def save_jester_selections(self, jester_window):
        pass

    def check_biome_in_logs(self):
        try:

            log_file_path = self.get_latest_log_file()
            if not log_file_path:
                return

            if not os.path.exists(log_file_path):
                return

            file_size = os.path.getsize(log_file_path)
            if file_size == 0:
                return

            if not hasattr(self, 'last_log_position'):

                with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as file:
                    file.seek(0, os.SEEK_END)  
                    self.last_log_position = file.tell()
                self.append_log(f"Initialized log position at the end of file: {os.path.basename(log_file_path)}")
                return  

            with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as file:

                file.seek(self.last_log_position)

                lines = file.readlines()

                self.last_log_position = file.tell()

            if not lines:
                return

            username = None
            for line in lines:
                if "Player.Name" in line or "PlayerName" in line or "Username" in line or "DisplayName" in line:

                    match = re.search(r'[Pp]layer\.?[Nn]ame\s*=\s*["\']([^"\']+)["\']|[Uu]sername["\']:\s*["\']([^"\']+)["\']|[Dd]isplay[Nn]ame["\']:\s*["\']([^"\']+)["\']', line)
                    if match:
                        username = next((g for g in match.groups() if g), None)
                        if username:
                            self.append_log(f"Extracted username from log: {username}")
                            break

            if not username:
                try:

                    file_name = os.path.basename(log_file_path)

                    if "T" in file_name and "Z" in file_name:

                        username = "Unknown"
                        self.append_log("Log filename contains timestamp, not using as username")
                    elif "Player" in file_name and "_" in file_name:

                        match = re.search(r'Player_(\d+)', file_name)
                        if match:
                            player_id = match.group(1)
                            username = f"Player_{player_id}"
                            self.append_log(f"Extracted player ID from filename: {username}")
                        else:
                            username = "Unknown"
                            self.append_log("Could not extract player ID from filename")
                    else:
                        username = "Unknown"
                        self.append_log("Could not extract username from filename")
                except Exception as e:
                    self.error_logging(e, "Error extracting username from file name")
                    username = "Unknown"

            if not username:
                username = "Unknown"
                self.append_log("Could not extract username, using 'Unknown'")

            biome_found = False

            for line in lines:
                line_upper = line.upper()  

                if "[BloxstrapRPC]" in line:
                    biome = self.get_biome_from_rpc(line)
                    if biome:
                        self.append_log(f"Found biome {biome} in RPC message")
                        self.handle_account_biome_detection(username, biome)
                        biome_found = True
                        continue

                if biome_found:
                    biome_found = False  
                    continue

                for biome in self.biome_data:
                    biome_upper = biome.upper()

                    if biome_upper in line_upper and any([
                        f"BIOME: {biome_upper}" in line_upper,
                        f"BIOME {biome_upper}" in line_upper,
                        f"ENTERED {biome_upper}" in line_upper,
                        f"BIOME:{biome_upper}" in line_upper,
                        f"CURRENT BIOME: {biome_upper}" in line_upper,
                        f"CURRENT BIOME {biome_upper}" in line_upper,
                        f"BIOME CHANGED TO {biome_upper}" in line_upper,
                        f"BIOME CHANGED: {biome_upper}" in line_upper,
                        f"BIOME TYPE: {biome_upper}" in line_upper,
                        f"BIOME TYPE {biome_upper}" in line_upper,
                        f"ENVIRONMENT: {biome_upper}" in line_upper,
                        f"ENVIRONMENT {biome_upper}" in line_upper
                    ]):
                        self.append_log(f"Found biome {biome} in log with specific pattern match")
                        self.handle_account_biome_detection(username, biome)
                        biome_found = True
                        break  

                if biome_found:
                    biome_found = False  
                    continue

                for biome in self.biome_data:
                    biome_upper = biome.upper()
                    if any([
                        f'"{biome_upper}"' in line_upper,
                        f"'{biome_upper}'" in line_upper,
                        f"[{biome_upper}]" in line_upper,
                        f"({biome_upper})" in line_upper,
                        f"<{biome_upper}>" in line_upper,
                        f"«{biome_upper}»" in line_upper
                    ]):
                        self.append_log(f"Found biome {biome} in log with quoted pattern match")
                        self.handle_account_biome_detection(username, biome)
                        biome_found = True
                        break  

                if biome_found:
                    biome_found = False  
                    continue

                for biome in self.biome_data:
                    biome_upper = biome.upper()

                    if (f" {biome_upper} " in line_upper or 
                        line_upper.startswith(f"{biome_upper} ") or 
                        line_upper.endswith(f" {biome_upper}") or
                        line_upper == biome_upper):
                        self.append_log(f"Found biome {biome} in log with word boundary match")
                        self.handle_account_biome_detection(username, biome)
                        biome_found = True
                        break  

        except Exception as e:
            error_msg = f"Error in check_biome_in_logs: {str(e)}"
            self.append_log(error_msg)
            self.error_logging(e, error_msg)

    def handle_biome_detection(self, biome):
        """Handle detection of a biome in the logs"""
        if not biome or biome not in self.biome_data:
            self.append_log(f"Invalid biome detected: {biome}")
            return

        def biome_detect_thread():
            try:

                if self.current_biome != biome:
                    biome_info = self.biome_data[biome]
                    now = datetime.now()

                    print(f"Detected Biome: {biome}, Color: {biome_info['color']}")
                    self.append_log(f"Detected Biome: {biome}")

                    previous_biome = self.current_biome

                    self.current_biome = biome

                    if biome not in self.biome_counts:
                        self.biome_counts[biome] = 0
                    self.biome_counts[biome] += 1

                    self.update_stats()

                    message_type = self.config.get("biome_notifier", {}).get(biome, "None")

                    if biome in ["GLITCHED", "DREAMSPACE"]:
                        message_type = "Ping"
                        if self.config.get("record_rare_biome", False): 
                            self.trigger_biome_record()

                    if previous_biome and previous_biome in self.biome_data:
                        prev_message_type = self.config.get("biome_notifier", {}).get(previous_biome, "None")
                        if prev_message_type != "None":
                            self.append_log(f"Sending end webhook for previous biome: {previous_biome}")
                            self.send_webhook(previous_biome, prev_message_type, "end")

                    if message_type != "None":
                        self.append_log(f"Sending start webhook for biome: {biome}")
                        self.send_webhook(biome, message_type, "start")

                    if biome in ["GLITCHED"] and self.config.get("auto_pop_glitched", False):
                        self.append_log("Auto-popping buffs for glitched biome")

            except Exception as e:
                error_msg = f"Error in handle_biome_detection for biome: {biome}"
                self.append_log(error_msg)
                self.error_logging(e, error_msg)

        threading.Thread(target=biome_detect_thread, daemon=True).start()

    def send_webhook(self, biome, message_type, event_type):
        """Send a webhook notification for a biome detection"""
        webhooks = self.config.get("webhooks", [])
        if not webhooks:
            self.append_log("No webhook URLs configured in config.json")
            return

        if message_type == "None": 
            return

        biome_info = self.biome_data[biome]
        biome_color = int(biome_info["color"], 16)
        timestamp = time.strftime("[%H:%M:%S]") 
        icon_url = "https://i.postimg.cc/mDzwFfX1/GLITCHED.png"

        content = ""

        if event_type == "start" and biome in ["GLITCHED", "DREAMSPACE"]:
            content = "@everyone"

        if event_type == "start":
            title = f"🌟 {biome} Biome Started 🌟"
        else:
            title = f"🔚 {biome} Biome Ended 🔚"

        description = f"## {timestamp} Biome Detected\n"
        if "description" in biome_info:
            description += f"### {biome_info['description']}\n"

        biome_count = self.biome_counts.get(biome, 0)
        description += f"\n**Total {biome} biomes detected:** {biome_count}"

        fields = []
        if event_type == "start":
            private_server_link = self.config.get("private_server_link", "")
            if private_server_link == "":
                private_server_link = "No link provided"

            fields.append({
                "name": "🔗 Private Server Link",
                "value": private_server_link,
                "inline": False
            })

            fields.append({
                "name": "📊 Session Stats",
                "value": f"Session Length: {self.get_total_session_time()}",
                "inline": True
            })

        embed = {
            "title": title,
            "description": description,
            "color": biome_color,
            "footer": {
                "text": f"BiomeScope | Biome Tracker • v{self.version}",
                "icon_url": icon_url
            },
            "fields": fields,
            "timestamp": None
        }

        if event_type == "start":
            embed["thumbnail"] = {"url": biome_info["thumbnail_url"]}

        webhook_success = False
        for webhook in webhooks:
            try:
                webhook_url = webhook.get("url", "").strip()
                if not webhook_url:
                                        continue

                response = requests.post(
                    webhook_url,
                    json={
                        "content": content,
                        "embeds": [embed]
                    },
                    headers={"Content-Type": "application/json"},
                    timeout=10  
                )
                response.raise_for_status()
                print(f"Sent {message_type} for {biome} - {event_type} to webhook")
                self.append_log(f"Sent {message_type} for {biome} - {event_type} to webhook")
                webhook_success = True
            except requests.exceptions.RequestException as e:
                error_msg = f"Failed to send webhook: {str(e)}"
                print(error_msg)
                self.append_log(error_msg)
                self.error_logging(e, f"Failed to send webhook for {biome}")

        if not webhook_success and webhooks:
            self.append_log(f"WARNING: Failed to send webhook notifications for {biome}")
            print(f"WARNING: Failed to send webhook notifications for {biome}")

    def test_webhook(self, webhook_url):
        if not webhook_url:
            messagebox.showerror("Error", "Please enter a webhook URL first.")
            return

        try:

            test_embed = {
                "title": "🧪 Webhook Test",
                "description": "This is a test message to verify your webhook is working correctly.",
                "color": 0x00FF00,  
                "footer": {
                    "text": f"BiomeScope | Version {self.version}",
                    "icon_url": "https://i.postimg.cc/mDzwFfX1/GLITCHED.png"
                },
                "timestamp": None
            }

            response = requests.post(
                webhook_url,
                json={
                    "content": "Webhook test message",
                    "embeds": [test_embed]
                },
                headers={"Content-Type": "application/json"},
                timeout=10
            )

            response.raise_for_status()
            messagebox.showinfo("Success", "Test message sent successfully!")
            self.append_log(f"Test webhook message sent successfully to {webhook_url}")
            return True
        except Exception as e:
            error_message = f"Failed to send test webhook: {str(e)}"
            messagebox.showerror("Error", error_message)
            self.append_log(error_message)
            self.error_logging(e, "Failed to send test webhook")
        return False

    def biome_loop_check(self):
        try:

            self.check_biome_in_logs()

            if self.config.get("enable_aura_detection", False):
                log_file_path = self.get_latest_log_file()
                if log_file_path:
                    self.check_aura_in_logs(log_file_path)

        except Exception as e:
            error_msg = f"Error in biome_loop_check: {str(e)}"
            self.append_log(error_msg)
            self.error_logging(e, error_msg)

    def multi_account_biome_loop(self):
        """Check for biomes in logs for multiple accounts"""
        try:

            if not hasattr(self, 'accounts') or not self.accounts:
                self.accounts = self.config.get("accounts", [])
                self.append_log(f"Loading accounts in multi_account_biome_loop: {len(self.accounts)} accounts found")

            if not hasattr(self, 'account_biomes'):
                self.account_biomes = {}

            if not hasattr(self, 'account_last_positions'):
                self.account_last_positions = {}

            if not hasattr(self, 'account_last_sent'):
                self.account_last_sent = {}

            if not hasattr(self, 'timestamp_logged_files'):
                self.timestamp_logged_files = set()

            check_count = 0

            while self.detection_running:
                try:
                    check_count += 1
                    log_verbose = (check_count % 10 == 1)  

                    if not self.accounts:
                        time.sleep(5)  
                        continue

                    for i, account in enumerate(self.accounts):
                        username = account.get("username")
                        if not username:
                            continue

                        if log_verbose:
                            self.append_log(f"Checking biomes for account {i+1}/{len(self.accounts)}: {username}")

                        log_file = self.get_log_file_for_user(username)

                        if not log_file:
                            if log_verbose:
                                self.append_log(f"No log file found for account: {username}")
                            continue

                        if log_verbose:
                            self.append_log(f"Using log file for {username}: {os.path.basename(log_file)}")

                        self.check_account_biome_in_logs(username, log_file)

                    time.sleep(5)

                except Exception as e:
                    error_msg = f"Error in multi_account_biome_loop cycle: {str(e)}"
                    self.append_log(error_msg)
                    self.error_logging(e, error_msg)
                    time.sleep(5)  

            self.append_log("Multi-account biome detection loop stopped")

        except Exception as e:
            error_msg = f"Error in multi_account_biome_loop: {str(e)}"
            self.append_log(error_msg)
            self.error_logging(e, error_msg)
            time.sleep(5)  

    def check_account_biome_in_logs(self, username, log_file_path):
        """Check for biomes in the log files for a specific account"""
        try:
            if not username:
                self.append_log("No username provided for account biome check")
                return

            if not log_file_path:
                self.append_log(f"No log file provided for account: {username}")
                return

            if not os.path.exists(log_file_path):
                self.append_log(f"Log file does not exist for account {username}: {log_file_path}")
                return

            file_size = os.path.getsize(log_file_path)
            if file_size == 0:
                self.append_log(f"Log file is empty for account {username}: {log_file_path}")
                return

            if username not in self.account_biomes:
                self.account_biomes[username] = None

            if not hasattr(self, 'account_last_positions'):
                self.account_last_positions = {}

            if username not in self.account_last_positions:

                self.account_last_positions[username] = max(0, file_size - 5000)  

            current_position = self.account_last_positions.get(username, 0)

            with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as file:

                if current_position > file_size:
                    self.append_log(f"Log file {log_file_path} has been truncated or rotated, resetting position")
                    current_position = max(0, file_size - 5000)  

                file.seek(current_position)

                lines = file.readlines()

                self.account_last_positions[username] = file.tell()

            if not lines:
                return

            detected_biomes = set()

            for line in lines:
                line_upper = line.upper()  

                if "[BloxstrapRPC]" in line:
                    biome = self.get_biome_from_rpc(line)
                    if biome and biome not in detected_biomes:
                        self.append_log(f"Found biome {biome} in RPC message for {username}")
                        self.handle_account_biome_detection(username, biome)
                        detected_biomes.add(biome)
                        continue

                for biome in self.biome_data:
                    if biome in detected_biomes:
                        continue  

                    biome_upper = biome.upper()

                    if biome_upper in line_upper and any([
                        f"BIOME: {biome_upper}" in line_upper,
                        f"BIOME {biome_upper}" in line_upper,
                        f"ENTERED {biome_upper}" in line_upper,
                        f"BIOME:{biome_upper}" in line_upper,
                        f"CURRENT BIOME: {biome_upper}" in line_upper,
                        f"CURRENT BIOME {biome_upper}" in line_upper,
                        f"BIOME CHANGED TO {biome_upper}" in line_upper,
                        f"BIOME CHANGED: {biome_upper}" in line_upper,
                        f"BIOME TYPE: {biome_upper}" in line_upper,
                        f"BIOME TYPE {biome_upper}" in line_upper,
                        f"ENVIRONMENT: {biome_upper}" in line_upper,
                        f"ENVIRONMENT {biome_upper}" in line_upper
                    ]):
                        self.append_log(f"Found biome {biome} in log for {username} with specific pattern match")
                        self.handle_account_biome_detection(username, biome)
                        detected_biomes.add(biome)
                        break  

                for biome in self.biome_data:
                    if biome in detected_biomes:
                        continue  

                    biome_upper = biome.upper()
                    if any([
                        f'"{biome_upper}"' in line_upper,
                        f"'{biome_upper}'" in line_upper,
                        f"[{biome_upper}]" in line_upper,
                        f"({biome_upper})" in line_upper,
                        f"<{biome_upper}>" in line_upper,
                        f"«{biome_upper}»" in line_upper
                    ]):
                        self.append_log(f"Found biome {biome} in log for {username} with quoted pattern match")
                        self.handle_account_biome_detection(username, biome)
                        detected_biomes.add(biome)
                        break  

                for biome in self.biome_data:
                    if biome in detected_biomes:
                        continue  

                    biome_upper = biome.upper()

                    if (f" {biome_upper} " in line_upper or 
                        line_upper.startswith(f"{biome_upper} ") or 
                        line_upper.endswith(f" {biome_upper}") or
                        line_upper == biome_upper):
                        self.append_log(f"Found biome {biome} in log for {username} with word boundary match")
                        self.handle_account_biome_detection(username, biome)
                        detected_biomes.add(biome)

        except Exception as e:
            error_msg = f"Error in check_account_biome_in_logs for user: {username} - {str(e)}"
            self.append_log(error_msg)
            self.error_logging(e, error_msg)

    def handle_account_biome_detection(self, username, biome):
        """Handle detection of a biome in the logs for a specific account"""
        if not username:
            self.append_log("No username provided for biome detection")
            return

        if not biome or biome not in self.biome_data:
            self.append_log(f"Invalid biome detected for {username}: {biome}")
            return

        def biome_detect_thread():
            try:

                if not hasattr(self, 'accounts') or not self.accounts:
                    self.accounts = self.config.get("accounts", [])
                    self.append_log(f"Loading accounts in biome_detect_thread: {len(self.accounts)} accounts found")

                self.append_log(f"Processing biome detection for {username}: {biome}")

                if username not in self.account_biomes:
                    self.account_biomes[username] = None
                    self.append_log(f"Initialized account_biomes for {username}")

                if username not in self.account_last_sent:
                    self.account_last_sent[username] = {b: datetime.min for b in self.biome_data}
                    self.append_log(f"Initialized account_last_sent for {username}")

                current_biome = self.account_biomes.get(username)
                previous_biome = current_biome

                if biome != current_biome:

                    now = datetime.now()
                    last_sent_time = self.account_last_sent[username].get(biome, datetime.min)
                    time_since_last_sent = (now - last_sent_time).total_seconds()

                    if time_since_last_sent < 30:
                        self.append_log(f"Ignoring biome detection for {username}: {biome} (cooldown period: {30 - time_since_last_sent:.1f}s remaining)")
                        return

                    self.append_log(f"Biome change detected for {username}: {current_biome} -> {biome}")

                    if biome in self.biome_data:
                        self.biome_counts[biome] = self.biome_counts.get(biome, 0) + 1
                        self.config["biome_counts"] = self.biome_counts
                        self.save_config()

                    self.account_biomes[username] = biome

                    self.account_last_sent[username][biome] = now

                    message_type = self.config.get("biome_notifier", {}).get(biome, "None")

                    if previous_biome and previous_biome in self.biome_data:
                        prev_message_type = self.config.get("biome_notifier", {}).get(previous_biome, "None")
                        if prev_message_type != "None" and self.config.get("BiomeEnd", True):
                            self.append_log(f"Sending end webhook for {username}'s previous biome: {previous_biome}")
                            self.send_account_webhook(username, previous_biome, prev_message_type, "end")

                    if message_type != "None" and biome != "Normal":
                        self.append_log(f"Sending start webhook for {username}'s biome: {biome}")
                        self.send_account_webhook(username, biome, message_type, "start")

                    if biome in ["GLITCHED"] and self.config.get("auto_pop_glitched", False):
                        self.append_log(f"Auto-popping buffs for {username}'s glitched biome")

            except Exception as e:
                error_msg = f"Error in handle_account_biome_detection for {username}: {str(e)}"
                self.append_log(error_msg)
                self.error_logging(e, error_msg)

        threading.Thread(target=biome_detect_thread, daemon=True).start()

    def open_accounts_manager(self):
        """Open the accounts manager window to add/edit/remove accounts"""
        accounts_window = ttk.Toplevel(self.root)
        accounts_window.title("Accounts Manager")
        accounts_window.geometry("700x500")
        accounts_window.resizable(True, True)

        main_frame = ttk.Frame(accounts_window)
        main_frame.pack(fill='both', expand=True, padx=10, pady=10)

        header_label = ttk.Label(main_frame, text="Manage Multiple Accounts", font=("Arial", 14, "bold"))
        header_label.pack(anchor='w', pady=(0, 10))

        help_text = ttk.Label(main_frame, 
                             text="Add accounts to track multiple Roblox instances. Each account needs a username and optional private server link.",
                             wraplength=650)
        help_text.pack(fill='x', pady=(0, 10))

        container_frame = ttk.Frame(main_frame)
        container_frame.pack(fill='both', expand=True, pady=5)

        canvas = tk.Canvas(container_frame, highlightthickness=0, 
                          bg=ttk.Style().lookup('TFrame', 'background'))

        scrollbar = ttk.Scrollbar(container_frame, orient="vertical", command=canvas.yview)

        accounts_frame = ttk.Frame(canvas)

        def update_scroll_region(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        accounts_frame.bind("<Configure>", update_scroll_region)

        canvas.create_window((0, 0), window=accounts_frame, anchor="nw", width=670)
        canvas.configure(yscrollcommand=scrollbar.set)

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")

        canvas.bind("<MouseWheel>", _on_mousewheel)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self.account_entries = []

        def add_account_entry(account=None):

            username = ""
            ps_link = ""

            if account:
                username = account.get("username", "")
                ps_link = account.get("ps_link", "")

            entry_frame = ttk.Frame(accounts_frame)
            entry_frame.pack(fill='x', pady=5)

            username_label = ttk.Label(entry_frame, text="Username:", width=10)
            username_label.pack(side='left', padx=(0, 5))

            username_entry = ttk.Entry(entry_frame, width=20)
            username_entry.pack(side='left', padx=5)
            username_entry.insert(0, username)

            ps_link_label = ttk.Label(entry_frame, text="PS Link:", width=8)
            ps_link_label.pack(side='left', padx=(10, 5))

            ps_link_entry = ttk.Entry(entry_frame, width=30)
            ps_link_entry.pack(side='left', fill='x', expand=True, padx=5)
            ps_link_entry.insert(0, ps_link)

            def remove_account():
                entry_frame.destroy()
                self.account_entries.remove((username_entry, ps_link_entry))

            remove_btn = ttk.Button(entry_frame, text="Remove", 
                                   command=remove_account,
                                   style="danger.TButton")
            remove_btn.pack(side='right', padx=5)

            self.account_entries.append((username_entry, ps_link_entry))

        for account in self.accounts:
            add_account_entry(account)

        add_btn = ttk.Button(main_frame, text="Add Account", 
                            command=lambda: add_account_entry(),
                            style="info.TButton")
        add_btn.pack(anchor='w', pady=10)

        def save_accounts():

            self.accounts = []
            for username_entry, ps_link_entry in self.account_entries:
                username = username_entry.get().strip()
                ps_link = ps_link_entry.get().strip()

                if username:  
                    self.accounts.append({
                        "username": username,
                        "ps_link": ps_link
                    })

            self.save_config()

            accounts_window.destroy()

            messagebox.showinfo("Success", f"Saved {len(self.accounts)} accounts.")

        save_btn = ttk.Button(main_frame, text="Save", 
                             command=save_accounts,
                             style="success.TButton")
        save_btn.pack(side='right', pady=10)

        cancel_btn = ttk.Button(main_frame, text="Cancel", 
                               command=accounts_window.destroy,
                               style="danger.TButton")
        cancel_btn.pack(side='right', padx=10, pady=10)

    def send_webhook_status(self, status, color=None):
        """Send a status update to the webhook"""
        webhooks = self.config.get("webhooks", [])
        if not webhooks:
            self.append_log("No webhook URLs configured in config.json")
            return

        if color is None:
            color = 0x00FF00  

        timestamp = time.strftime("[%H:%M:%S]")
        icon_url = "https://i.postimg.cc/mDzwFfX1/GLITCHED.png"

        title = f"📊 Status Update"
        description = f"## {timestamp} {status}\n"

        if self.accounts:
            description += "\n### Tracked Accounts:\n"
            for account in self.accounts:
                username = account.get("username", "Unknown")
                description += f"- {username}\n"

        embed = {
            "title": title,
            "description": description,
            "color": color,
            "footer": {
                "text": f"BiomeScope | Version {self.version}",
                "icon_url": icon_url
            },
            "timestamp": None
        }

        webhook_success = False
        for webhook in webhooks:
            try:
                webhook_url = webhook.get("url", "").strip()
                if not webhook_url:
                    continue

                response = requests.post(
                    webhook_url,
                    json={
                        "embeds": [embed]
                    },
                    headers={"Content-Type": "application/json"},
                    timeout=10  
                )
                response.raise_for_status()
                self.append_log(f"Sent status webhook: {status}")
                webhook_success = True
            except requests.exceptions.RequestException as e:
                error_msg = f"Failed to send status webhook: {str(e)}"
                self.append_log(error_msg)
                self.error_logging(e, "Failed to send status webhook")

        if not webhook_success and webhooks:
            self.append_log(f"WARNING: Failed to send status webhook: {status}")
            print(f"WARNING: Failed to send status webhook: {status}")

    def biome_itemchange_loop(self):
        """Loop for detecting biome via item changes - Removed for simplified version"""
        pass

    def auto_biome_change(self):
        """Auto change biome - Removed for simplified version"""
        pass

    def use_item(self, item_name):
        """Use an item - Removed for simplified version"""
        pass

    def send_account_webhook(self, username, biome, message_type, event_type):
        """Send a webhook notification for an account's biome detection"""
        webhooks = self.config.get("webhooks", [])
        if not webhooks:
            self.append_log("No webhook URLs configured in config.json")
            return

        if message_type == "None":
            return

        current_time = time.time()
        time_since_last_webhook = current_time - self.last_webhook_time
        if time_since_last_webhook < self.webhook_rate_limit:

            sleep_time = self.webhook_rate_limit - time_since_last_webhook
            self.append_log(f"Rate limiting webhook for {username}'s {biome}, waiting {sleep_time:.2f} seconds")
            time.sleep(sleep_time)

        self.last_webhook_time = time.time()

        biome_info = self.biome_data[biome]
        biome_color = int(biome_info["color"], 16)

        unix_timestamp = int(time.time())
        timestamp_full = f"<t:{unix_timestamp}:F>"  
        timestamp_relative = f"<t:{unix_timestamp}:R>"  

        icon_url = "https://i.postimg.cc/mDzwFfX1/GLITCHED.png"

        ps_link = self.get_ps_link_for_user(username)

        content = ""
        if event_type == "start":
            if ps_link:
                content = f"**Private Server Link:** {ps_link}"
            else:
                content = "**No Private Server Link Provided**"

            if biome in ["GLITCHED", "DREAMSPACE"]:
                user_id = self.config.get(f"{biome}ID", "")
                if not user_id:
                    user_id = self.config.get("UserID", "")

                if user_id:
                    content += f" <@{user_id}>"

        biome_emoji = {
            "SNOWY": "❄️",
            "WINDY": "🌪️",
            "RAINY": "🌧️",
            "FOGGY": "🌫️",
            "SUNNY": "☀️",
            "GLITCHED": "🌈",
            "DREAMSPACE": "✨",
            "NORMAL": "🌱"
        }.get(biome.upper(), "🌍")

        if event_type == "start":
            title = f"{biome_emoji} {biome} Biome Started"
        else:
            title = f"{biome_emoji} {biome} Biome Ended"

        description = f"**Account:** `{username}`\n"
        description += f"**Time:** {timestamp_full} ({timestamp_relative})\n"

        if event_type == "start":
            description += f"**Status:** Active ✅\n"
        else:
            description += f"**Status:** Ended ⏹️\n"

        if "description" in biome_info:
            description += f"\n{biome_info['description']}\n"

        embed = {
            "title": title,
            "description": description,
            "color": biome_color,
            "footer": {
                "text": f"BiomeScope | Version {self.version}",
                "icon_url": icon_url
            },
            "timestamp": None
        }

        if "thumbnail_url" in biome_info:
            embed["thumbnail"] = {"url": biome_info["thumbnail_url"]}

        embed["author"] = {
            "name": "Biome Update",
            "icon_url": "https://i.postimg.cc/mDzwFfX1/GLITCHED.png"
        }

        webhook_success = False
        for webhook in webhooks:
            try:
                webhook_url = webhook.get("url", "").strip()
                if not webhook_url:
                    continue

                self.append_log(f"Sending webhook for {username}'s {biome} with PS link: {ps_link}")

                response = requests.post(
                    webhook_url,
                    json={
                        "content": content,
                        "embeds": [embed]
                    },
                    headers={"Content-Type": "application/json"},
                    timeout=10  
                )
                response.raise_for_status()
                print(f"Sent {message_type} for {username}'s {biome} - {event_type} to webhook")
                self.append_log(f"Sent {message_type} for {username}'s {biome} - {event_type} to webhook")
                webhook_success = True

                time.sleep(0.5)
            except requests.exceptions.RequestException as e:
                error_msg = f"Failed to send webhook for {username}: {str(e)}"
                print(error_msg)
                self.append_log(error_msg)
                self.error_logging(e, f"Failed to send webhook for {username}'s {biome}")

                if "429" in str(e):
                    self.webhook_rate_limit = min(self.webhook_rate_limit * 1.5, 5.0)  
                    self.append_log(f"Increased webhook rate limit to {self.webhook_rate_limit:.2f} seconds due to rate limiting")
                    time.sleep(2.0)  

        if not webhook_success and webhooks:
            self.append_log(f"WARNING: Failed to send webhook notifications for {username}'s {biome}")
            print(f"WARNING: Failed to send webhook notifications for {username}'s {biome}")

    def get_ps_link_for_user(self, username):
        """Get the private server link for a specific user"""
        if not username:
            return self.config.get("private_server_link", "")

        for account in self.accounts:
            if account.get("username") == username:
                return account.get("ps_link", "")

        return self.config.get("private_server_link", "")

    def start_detection(self):
        """Start the biome detection process - simplified version"""

        if hasattr(self, 'detection_running') and self.detection_running:
            self.append_log("Detection is already running")
            return

        self.detection_running = True
        self.start_time = datetime.now()
        self.append_log("Starting biome detection...")

        if not hasattr(self, 'accounts') or not self.accounts:
            self.accounts = self.config.get("accounts", [])
            self.append_log(f"Loaded {len(self.accounts)} accounts from config in start_detection")

        self.account_biomes = {}
        self.account_last_positions = {}
        self.account_last_sent = {}

        if not hasattr(self, 'logs'):
            self.logs = []

        self.root.title("BiomeScope | Version 1.0.1-Beta (Running)")

        self.detection_thread = threading.Thread(target=self.multi_account_biome_loop, daemon=True)
        self.detection_thread.start()
        self.append_log("Multi-account biome detection thread started")

        self.send_webhook_status("Biome Detection Started", 0x00FF00)  
        self.append_log("Biome detection started successfully")
        print("Biome detection started.")

    def stop_detection(self):
        """Stop the biome detection process - simplified version"""
        if not hasattr(self, 'detection_running') or not self.detection_running:
            self.append_log("Detection is not running")
            return

        self.detection_running = False
        self.append_log("Stopping biome detection...")

        if hasattr(self, 'start_time') and self.start_time:
            elapsed_time = int((datetime.now() - self.start_time).total_seconds())
            self.saved_session = elapsed_time  
            self.start_time = None

        self.save_config()

        self.root.title("BiomeScope | Version 1.0.1-Beta (Stopped)")

        self.send_webhook_status("Biome Detection Stopped", 0xFF0000)  

        self.current_biome = None
        self.account_biomes = {}

        self.append_log("Biome detection stopped successfully")
        print("Biome detection stopped.")

    def get_log_file_for_user(self, username):
        """Get the log file for a specific user"""
        if not username:
            self.append_log("No username provided for log file search")
            return None

        try:
            if not os.path.exists(self.logs_dir):
                self.append_log(f"Logs directory not found: {self.logs_dir}")
                return None

            files = []
            try:
                for f in os.listdir(self.logs_dir):
                    if f.endswith('.log') and ('last' in f.lower() or 'player' in f.lower()):
                        full_path = os.path.join(self.logs_dir, f)

                        if os.path.isfile(full_path) and os.path.getsize(full_path) > 0:
                            files.append(full_path)
            except Exception as e:
                self.error_logging(e, f"Error listing log files for user: {username}")
                return None

            if not files:

                if not hasattr(self, 'no_files_logged') or time.time() - self.no_files_logged.get(username, 0) > 300:
                    self.append_log(f"No valid log files found for user: {username}")
                    if not hasattr(self, 'no_files_logged'):
                        self.no_files_logged = {}
                    self.no_files_logged[username] = time.time()
                return None

            files.sort(key=os.path.getmtime, reverse=True)

            username_patterns = [
                username,
                f'"{username}"', 
                f"'{username}'", 
                f">{username}<",
                f'DisplayName":"{username}"',
                f'displayName":"{username}"',
                f'Username":"{username}"',
                f'username":"{username}"',
                f'Name":"{username}"',
                f'name":"{username}"',
                f'Player.Name = "{username}"',
                f'Player.Name="{username}"',
                f'PlayerName="{username}"',
                f'PlayerName = "{username}"'
            ]

            if not hasattr(self, 'verified_log_files'):
                self.verified_log_files = {}

            if username in self.verified_log_files:
                verified_file = self.verified_log_files[username]
                if verified_file in files:

                    return verified_file

            if hasattr(self, 'username_log_cache') and username in self.username_log_cache:
                cached_file = self.username_log_cache[username]
                if cached_file in files:

                    self.verified_log_files[username] = cached_file
                    return cached_file

            if not hasattr(self, 'username_log_cache'):
                self.username_log_cache = {}

            for file_path in files:
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:

                        content = file.read(50000)  

                        if any(pattern in content for pattern in username_patterns):

                            self.append_log(f"Found log file for {username} (pattern match): {os.path.basename(file_path)}")

                            self.username_log_cache[username] = file_path

                            self.verified_log_files[username] = file_path
                            return file_path

                except Exception as e:
                    self.error_logging(e, f"Error reading log file: {file_path}")
                    continue

            if not hasattr(self, 'no_match_logged') or time.time() - self.no_match_logged.get(username, 0) > 300:
                self.append_log(f"No log file found containing username: {username}")
                if not hasattr(self, 'no_match_logged'):
                    self.no_match_logged = {}
                self.no_match_logged[username] = time.time()

            if files:

                available_file = None
                for file_path in files:
                    file_already_assigned = False
                    if hasattr(self, 'username_log_cache'):
                        for other_user, other_file in self.username_log_cache.items():
                            if other_file == file_path:
                                file_already_assigned = True
                                break

                    if not file_already_assigned:
                        available_file = file_path
                        break

                if available_file:
                    self.append_log(f"Assigning available log file to {username}: {os.path.basename(available_file)}")
                    self.username_log_cache[username] = available_file
                    return available_file
                else:

                    newest_file = files[0]
                    self.append_log(f"All log files are assigned. Using newest file for {username}: {os.path.basename(newest_file)}")
                    self.username_log_cache[username] = newest_file
                    return newest_file

            return None

        except Exception as e:
            error_msg = f"Error in get_log_file_for_user for {username}: {str(e)}"
            self.append_log(error_msg)
            self.error_logging(e, error_msg)
            return None

    def display_user_activity(self, username=None):
        """
        Display activity data for a user in a new window

        Args:
            username (str, optional): Username to display activity for. If None, will prompt user.
        """
        try:

            if not username:
                username = self.username_var.get().strip()

            if not username:
                messagebox.showwarning("Input Required", "Please enter a username to view activity data.")
                return

            self.status_label.config(text=f"Loading activity data for {username}...")
            self.root.update()

            result = self.get_user_activity_data(username)

            if not result['success']:
                messagebox.showerror("Error", result['message'])
                self.status_label.config(text="Ready")
                return

            activity_data = result['data']

            activity_window = tk.Toplevel(self.root)
            activity_window.title(f"Activity Data for {username}")
            activity_window.geometry("800x600")
            activity_window.minsize(800, 600)

            activity_window.configure(bg="#f0f0f0")

            header_frame = tk.Frame(activity_window, bg="#3a7ca5", padx=10, pady=10)
            header_frame.pack(fill=tk.X)

            tk.Label(
                header_frame, 
                text=f"Activity Report for {username}", 
                font=("Arial", 16, "bold"), 
                fg="white", 
                bg="#3a7ca5"
            ).pack(side=tk.LEFT)

            score_frame = tk.Frame(header_frame, bg="#3a7ca5")
            score_frame.pack(side=tk.RIGHT)

            score_value = activity_data.get('activity_score', 0)
            score_color = "#4CAF50" if score_value >= 70 else "#FFC107" if score_value >= 40 else "#F44336"

            tk.Label(
                score_frame,
                text="Activity Score:",
                font=("Arial", 12),
                fg="white",
                bg="#3a7ca5"
            ).pack(side=tk.LEFT, padx=(0, 5))

            tk.Label(
                score_frame,
                text=str(score_value),
                font=("Arial", 16, "bold"),
                fg=score_color,
                bg="#3a7ca5"
            ).pack(side=tk.LEFT)

            main_frame = tk.Frame(activity_window, bg="#f0f0f0", padx=20, pady=20)
            main_frame.pack(fill=tk.BOTH, expand=True)

            canvas = tk.Canvas(main_frame, bg="#f0f0f0", highlightthickness=0)
            scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
            scrollable_frame = tk.Frame(canvas, bg="#f0f0f0")

            scrollable_frame.bind(
                "<Configure>",
                lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
            )

            canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
            canvas.configure(yscrollcommand=scrollbar.set)

            canvas.pack(side="left", fill="both", expand=True)
            scrollbar.pack(side="right", fill="y")

            summary_frame = tk.LabelFrame(scrollable_frame, text="Activity Summary", bg="#f0f0f0", font=("Arial", 12, "bold"), padx=10, pady=10)
            summary_frame.pack(fill=tk.X, pady=(0, 15))

            summary_grid = tk.Frame(summary_frame, bg="#f0f0f0")
            summary_grid.pack(fill=tk.X)

            summary_items = [
                ("Total Actions:", str(activity_data.get('total_actions', 0))),
                ("Active Days:", str(activity_data.get('active_days', 0))),
                ("First Activity:", activity_data.get('first_activity', "N/A")),
                ("Last Activity:", activity_data.get('last_activity', "N/A")),
                ("Log File:", activity_data.get('log_file', "N/A"))
            ]

            for i, (label, value) in enumerate(summary_items):
                tk.Label(summary_grid, text=label, font=("Arial", 11), bg="#f0f0f0", anchor="e").grid(row=i, column=0, sticky="e", padx=(0, 10), pady=2)
                tk.Label(summary_grid, text=value, font=("Arial", 11), bg="#f0f0f0", anchor="w").grid(row=i, column=1, sticky="w", pady=2)

            if activity_data.get('action_types'):
                action_frame = tk.LabelFrame(scrollable_frame, text="Action Types", bg="#f0f0f0", font=("Arial", 12, "bold"), padx=10, pady=10)
                action_frame.pack(fill=tk.X, pady=(0, 15))

                action_bars_frame = tk.Frame(action_frame, bg="#f0f0f0")
                action_bars_frame.pack(fill=tk.X, pady=5)

                action_types = activity_data.get('action_types', {})
                sorted_actions = sorted(action_types.items(), key=lambda x: x[1], reverse=True)

                max_value = max(action_types.values()) if action_types else 1

                for i, (action, count) in enumerate(sorted_actions):
                    row_frame = tk.Frame(action_bars_frame, bg="#f0f0f0")
                    row_frame.pack(fill=tk.X, pady=2)

                    tk.Label(
                        row_frame, 
                        text=action.capitalize(), 
                        font=("Arial", 10), 
                        width=15, 
                        anchor="w",
                        bg="#f0f0f0"
                    ).pack(side=tk.LEFT)

                    bar_container = tk.Frame(row_frame, bg="#e0e0e0", height=20, width=400)
                    bar_container.pack(side=tk.LEFT, padx=5)

                    bar_width = int((count / max_value) * 400)

                    bar = tk.Frame(bar_container, bg="#3a7ca5", height=20, width=bar_width)
                    bar.place(x=0, y=0)

                    tk.Label(
                        row_frame,
                        text=str(count),
                        font=("Arial", 10),
                        bg="#f0f0f0"
                    ).pack(side=tk.LEFT, padx=5)

            daily_frame = tk.LabelFrame(scrollable_frame, text="Daily Activity", bg="#f0f0f0", font=("Arial", 12, "bold"), padx=10, pady=10)
            daily_frame.pack(fill=tk.X, pady=(0, 15))

            calendar_frame = tk.Frame(daily_frame, bg="#f0f0f0")
            calendar_frame.pack(fill=tk.X, pady=5)

            daily_activity = activity_data.get('daily_activity', {})

            max_daily = max([day_data['count'] for day_data in daily_activity.values()]) if daily_activity else 1

            sorted_dates = sorted(daily_activity.keys())

            weeks = []
            current_week = []

            for date_str in sorted_dates:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')

                if date_obj.weekday() == 0 and current_week:
                    weeks.append(current_week)
                    current_week = []

                current_week.append((date_str, daily_activity[date_str]))

            if current_week:
                weeks.append(current_week)

            for week in weeks:
                week_frame = tk.Frame(calendar_frame, bg="#f0f0f0")
                week_frame.pack(fill=tk.X, pady=2)

                for date_str, day_data in week:
                    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                    day_name = date_obj.strftime('%a')
                    day_num = date_obj.strftime('%d')

                    count = day_data['count']
                    intensity = min(1.0, count / max_daily) if max_daily > 0 else 0

                    r = int(240 - (intensity * 150))
                    g = int(248 - (intensity * 100))
                    b = int(255 - (intensity * 50))
                    color = f"#{r:02x}{g:02x}{b:02x}"

                    day_cell = tk.Frame(week_frame, bg=color, width=60, height=60, padx=5, pady=5, relief=tk.RAISED, borderwidth=1)
                    day_cell.pack(side=tk.LEFT, padx=2)
                    day_cell.pack_propagate(False)

                    tk.Label(
                        day_cell,
                        text=day_name,
                        font=("Arial", 8),
                        bg=color
                    ).pack(anchor="nw")

                    tk.Label(
                        day_cell,
                        text=day_num,
                        font=("Arial", 10, "bold"),
                        bg=color
                    ).pack(anchor="center")

                    count_label = tk.Label(
                        day_cell,
                        text=str(count),
                        font=("Arial", 9, "bold"),
                        bg=color
                    )
                    count_label.pack(anchor="s")

                    if count > 0:
                        actions_text = "\n".join([f"{action}: {count}" for action, count in day_data['actions'].items()])
                        tooltip_text = f"{date_str}\n{actions_text}"
                        create_tooltip(day_cell, tooltip_text)

            button_frame = tk.Frame(activity_window, bg="#f0f0f0", pady=10)
            button_frame.pack(fill=tk.X)

            close_button = tk.Button(
                button_frame,
                text="Close",
                command=activity_window.destroy,
                bg="#3a7ca5",
                fg="white",
                font=("Arial", 10, "bold"),
                padx=20,
                pady=5
            )
            close_button.pack()

            self.status_label.config(text="Ready")

        except Exception as e:
            error_msg = f"Error displaying activity data: {str(e)}"
            self.append_log(error_msg)
            self.error_logging(e, error_msg)
            messagebox.showerror("Error", error_msg)
            self.status_label.config(text="Ready")

    def refresh_log_files(self):
        """Refresh the list of log files in the treeview"""
        try:

            for item in self.log_files_tree.get_children():
                self.log_files_tree.delete(item)

            log_files = self.get_log_files()

            if not log_files:
                self.append_log("No log files found")
                return

            for file_path in log_files:
                try:
                    file_name = os.path.basename(file_path)
                    file_size = os.path.getsize(file_path)
                    file_modified = datetime.fromtimestamp(os.path.getmtime(file_path)).strftime('%Y-%m-%d %H:%M:%S')

                    if file_size < 1024:
                        size_str = f"{file_size} B"
                    elif file_size < 1024 * 1024:
                        size_str = f"{file_size / 1024:.1f} KB"
                    else:
                        size_str = f"{file_size / (1024 * 1024):.1f} MB"

                    self.log_files_tree.insert("", "end", values=(file_name, size_str, file_modified))
                except Exception as e:
                    self.error_logging(e, f"Error processing log file: {file_path}")
                    continue

            self.append_log(f"Found {len(log_files)} log files")

        except Exception as e:
            error_msg = f"Error refreshing log files: {str(e)}"
            self.append_log(error_msg)
            self.error_logging(e, error_msg)

    def get_log_files(self):
        """
        Get a list of log files from the logs directory

        Returns:
            list: List of log file paths sorted by modification time (newest first)
        """
        try:
            log_files = []

            if not os.path.exists(self.logs_dir):
                self.append_log(f"Logs directory not found: {self.logs_dir}")
                return log_files

            for file_name in os.listdir(self.logs_dir):
                file_path = os.path.join(self.logs_dir, file_name)

                if os.path.isfile(file_path) and file_name.endswith('.log'):
                    log_files.append(file_path)

            log_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)

            return log_files

        except Exception as e:
            error_msg = f"Error getting log files: {str(e)}"
            self.append_log(error_msg)
            self.error_logging(e, error_msg)
            return []

    def get_latest_log_file(self):
        """
        Get the most recently modified log file

        Returns:
            str: Path to the most recent log file, or None if no log files found
        """
        try:
            log_files = self.get_log_files()

            if not log_files:
                self.append_log("No log files found")
                return None

            return log_files[0]

        except Exception as e:
            error_msg = f"Error getting latest log file: {str(e)}"
            self.append_log(error_msg)
            self.error_logging(e, error_msg)
            return None

    def get_biome_from_rpc(self, rpc_message):
        """Extract biome name from RPC message, similar to AHK script's getBiome function"""
        try:
            if "[BloxstrapRPC]" not in rpc_message:
                return None

            if "largeImage" in rpc_message:

                large_image_part = rpc_message[rpc_message.find("largeImage")+10:]

                comma_pos = large_image_part.find(",")
                if comma_pos > 0:

                    biome_name = large_image_part[:comma_pos].strip('"\'{}:')

                    for biome in self.biome_data:
                        if biome.upper() == biome_name.upper():
                            return biome

            if "details" in rpc_message:
                details_part = rpc_message[rpc_message.find("details")+7:]
                colon_pos = details_part.find(":")
                if colon_pos > 0:
                    details_part = details_part[colon_pos+1:]
                    comma_pos = details_part.find(",")
                    if comma_pos > 0:
                        details_value = details_part[:comma_pos].strip('"\'{}:')
                    else:
                        details_value = details_part.strip('"\'{}:')

                    for biome in self.biome_data:
                        if biome.upper() in details_value.upper():
                            return biome

            if "state" in rpc_message:
                state_part = rpc_message[rpc_message.find("state")+5:]
                colon_pos = state_part.find(":")
                if colon_pos > 0:
                    state_part = state_part[colon_pos+1:]
                    comma_pos = state_part.find(",")
                    if comma_pos > 0:
                        state_value = state_part[:comma_pos].strip('"\'{}:')
                    else:
                        state_value = state_part.strip('"\'{}:')

                    for biome in self.biome_data:
                        if biome.upper() in state_value.upper():
                            return biome

            return None
        except Exception as e:
            self.error_logging(e, "Error extracting biome from RPC message")
            return None

def create_tooltip(widget, text):
    """Create a tooltip for a given widget with the specified text"""
    def enter(event):
        x, y, _, _ = widget.bbox("insert")
        x += widget.winfo_rootx() + 25
        y += widget.winfo_rooty() + 20

        tooltip = tk.Toplevel(widget)
        tooltip.wm_overrideredirect(True)
        tooltip.wm_geometry(f"+{x}+{y}")

        label = ttk.Label(tooltip, text=text, background="#2d2d2d", 
                        foreground="white", relief="solid", borderwidth=1,
                        padding=(5, 2))
        label.pack()

        widget._tooltip = tooltip

    def leave(event):
        if hasattr(widget, "_tooltip"):
            widget._tooltip.destroy()

    widget.bind("<Enter>", enter)
    widget.bind("<Leave>", leave)

def get_user_activity_data(self, username, days_back=30):
    """
    Retrieve and process activity data for a specific user from their log file

    Args:
        username (str): The username to get activity data for
        days_back (int): Number of days to look back for activity data

    Returns:
        dict: Dictionary containing processed activity data
    """
    try:
        self.append_log(f"Getting activity data for {username}, looking back {days_back} days")

        log_file = self.get_log_file_for_user(username)
        if not log_file:
            self.append_log(f"No log file found for {username}")
            return {
                'success': False,
                'message': f"No log file found for {username}",
                'data': {}
            }

        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)

        activity_data = {
            'daily_activity': {},
            'total_actions': 0,
            'action_types': {},
            'active_days': 0,
            'first_activity': None,
            'last_activity': None,
            'username': username,
            'log_file': os.path.basename(log_file)
        }

        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime('%Y-%m-%d')
            activity_data['daily_activity'][date_str] = {
                'count': 0,
                'actions': {}
            }
            current_date += timedelta(days=1)

        with open(log_file, 'r', encoding='utf-8', errors='ignore') as file:
            for line in file:
                try:

                    if username.lower() not in line.lower():
                        continue

                    match = re.search(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\].*?' + re.escape(username) + r'.*?(logged in|completed|submitted|viewed|accessed|downloaded|uploaded|modified)', line, re.IGNORECASE)
                    if not match:
                        continue

                    timestamp_str = match.group(1)
                    action = match.group(2).lower()

                    timestamp = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')

                    if timestamp < start_date or timestamp > end_date:
                        continue

                    date_str = timestamp.strftime('%Y-%m-%d')

                    activity_data['total_actions'] += 1

                    if action not in activity_data['action_types']:
                        activity_data['action_types'][action] = 0
                    activity_data['action_types'][action] += 1

                    if date_str in activity_data['daily_activity']:
                        activity_data['daily_activity'][date_str]['count'] += 1
                        if action not in activity_data['daily_activity'][date_str]['actions']:
                            activity_data['daily_activity'][date_str]['actions'][action] = 0
                        activity_data['daily_activity'][date_str]['actions'][action] += 1

                    if activity_data['first_activity'] is None or timestamp < datetime.strptime(activity_data['first_activity'], '%Y-%m-%d %H:%M:%S'):
                        activity_data['first_activity'] = timestamp_str

                    if activity_data['last_activity'] is None or timestamp > datetime.strptime(activity_data['last_activity'], '%Y-%m-%d %H:%M:%S'):
                        activity_data['last_activity'] = timestamp_str

                except Exception as e:
                    self.error_logging(e, f"Error processing log line for {username}")
                    continue

        for date_str, day_data in activity_data['daily_activity'].items():
            if day_data['count'] > 0:
                activity_data['active_days'] += 1

        activity_score = min(100, (activity_data['total_actions'] / 10) + (activity_data['active_days'] * 3))
        activity_data['activity_score'] = round(activity_score)

        self.append_log(f"Successfully processed activity data for {username}: {activity_data['total_actions']} actions over {activity_data['active_days']} active days")

        return {
            'success': True,
            'message': "Activity data retrieved successfully",
            'data': activity_data
        }

    except Exception as e:
        error_msg = f"Error getting activity data for {username}: {str(e)}"
        self.append_log(error_msg)
        self.error_logging(e, error_msg)
        return {
            'success': False,
            'message': error_msg,
            'data': {}
        }

try:
    biome_presence = BiomePresence()
except KeyboardInterrupt:
    print("Exited (Keyboard Interrupted)")
finally:

    if 'biome_presence' in locals() and hasattr(biome_presence, 'antiafk'):
        biome_presence.antiafk.shutdown()

    keyboard.unhook_all()