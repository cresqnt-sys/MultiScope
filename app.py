import os
import sys
import time
import threading
import keyboard 
import webbrowser 
import requests 
from datetime import datetime, timedelta
from collections import deque 
from configparser import ConfigParser 

from detection import DetectionManager
from utils import (
    error_logging, load_config, save_config, load_logs, save_logs,
    load_biome_data, load_auras_json, parse_session_time, format_session_time,
    setup_locale, setup_roblox_feature_flags, check_for_updates, download_update,
    get_ps_link_for_user, APP_NAME 
)

try:

    from antiafk import AntiAFK
    HAS_ANTIAFK = True
except ImportError:
    HAS_ANTIAFK = False
    print("AntiAFK module not found or failed to import. Anti-AFK features disabled.")
    AntiAFK = None 

APP_VERSION = "0.0.9-Alpha" 

class MultiScopeApp:
    def __init__(self, gui_manager_class=None):
        """Initialize the MultiScope Application.

        Args:
            gui_manager_class: The class to use for the GUI Manager.
                               Defaults to None, but should be provided by main.py.
        """
        self.version = APP_VERSION
        self.myappid = f"{APP_NAME}.App.{self.version}" 
        self.has_antiafk = HAS_ANTIAFK
        self.antiafk = None 

        self.detection_running = False
        self.stop_event = threading.Event()
        self.detection_thread = None
        self.config_changed = False 
        self.startup_timestamp = time.time() 
        self.program_start_time_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S") 

        self.biome_data = load_biome_data()
        self.auras_data = load_auras_json()
        self.config = load_config(list(self.biome_data.keys())) 
        self.logs = load_logs()
        self.accounts = self.config.get("accounts", [])
        self.biome_counts = self.config.get("biome_counts", {b: 0 for b in self.biome_data})
        self.active_accounts = set() 

        self.session_start_time = None
        self.saved_session_seconds = parse_session_time(self.config.get("session_time", "0:00:00"))
        self.session_timer_thread = None
        self.session_timer_stop_event = threading.Event()

        if self.has_antiafk:
             try:
                 self.antiafk = AntiAFK(self, self.config) 
             except Exception as e:
                 error_logging(e, "Failed to initialize AntiAFK module")
                 self.has_antiafk = False 

        self.detection_manager = DetectionManager(self)

        if gui_manager_class:
            self.gui_manager = gui_manager_class(self)
        else:

            raise ValueError("GuiManager class must be provided to MultiScopeApp")

        setup_locale()
        self._initialize_state()
        self._setup_hotkeys()

    def _initialize_state(self):
        """Initializes application state based on loaded config."""

        for biome in self.biome_data:
            if biome not in self.biome_counts:
                self.biome_counts[biome] = 0
        self.config["biome_counts"] = self.biome_counts 

        self.active_accounts = {acc.get("username", "").lower() for acc in self.accounts if acc.get("active") and acc.get("username")}

        if self.config.get("apply_feature_flags_on_startup", True): 
             modified_paths = setup_roblox_feature_flags()
             if modified_paths:
                  self.append_log(f"Applied Roblox feature flags to: {', '.join(modified_paths)}")

        self.detection_manager.reset_detection_states()

        print(f"Initialized with {len(self.accounts)} accounts, {len(self.active_accounts)} active.")

    def _setup_hotkeys(self):
         """Sets up global hotkeys using the keyboard library."""
         try:
             keyboard.add_hotkey('F1', self.start_detection)
             keyboard.add_hotkey('F2', self.stop_detection)

             print("Global hotkeys (F1=Start, F2=Stop) registered.")
         except Exception as e:
             error_logging(e, "Failed to register global hotkeys. They may not work.")

             if hasattr(self.gui_manager, 'show_message_box'):
                  self.gui_manager.show_message_box("Hotkey Error", "Failed to register global hotkeys (F1/F2). They may not function correctly. Ensure the application has necessary permissions.", "warning")

    def run(self):
        """Starts the application GUI and main loop."""

        if not hasattr(self, 'gui_manager') or not self.gui_manager:
             print("FATAL: GUI Manager not initialized.")
             return
        self.gui_manager.setup_gui()
        self.gui_manager.run() 

    def start_detection(self):
        """Starts the biome detection background thread."""
        if self.detection_running:
            self.append_log("⚠️ Detection already running!")
            return

        try:
            self.detection_running = True
            self.stop_event.clear()
            self.session_start_time = datetime.now() 
            self.program_start_time_iso = datetime.now().strftime("%Y-%m-%dT%H:%M:%S") 
            self.append_log(f"🚀 Starting detection at {self.session_start_time.strftime('%Y-%m-%d %H:%M:%S')}")
            self.append_log(f"Resetting log processing timestamp to: {self.program_start_time_iso}")

            self.detection_manager.reset_detection_states()

            self.detection_thread = threading.Thread(target=self._detection_loop, daemon=True)
            self.detection_thread.start()

            self.session_timer_stop_event.clear()
            self.session_timer_thread = threading.Thread(target=self._update_session_timer_loop, daemon=True)
            self.session_timer_thread.start()

            self.gui_manager.update_status("Running", "green")
            self.gui_manager.update_detection_buttons()
            if self.gui_manager.root: self.gui_manager.root.title(f"MultiScope | v{self.version} (Running)")

            self._send_status_webhook("MultiScope Started", 0x00FF00)

        except Exception as e:
             error_logging(e, "Error starting detection")
             self.detection_running = False 
             self.gui_manager.update_status("Error Starting", "red")
             self.gui_manager.update_detection_buttons()
             if self.gui_manager.root: self.gui_manager.root.title(f"MultiScope | v{self.version} (Error)")

    def stop_detection(self):
        """Stops the biome detection background thread."""
        if not self.detection_running:
            self.append_log("⚠️ Detection is not running!")
            return

        try:
            self.append_log("🛑 Stopping detection...")
            self.detection_running = False 
            self.stop_event.set() 
            self.session_timer_stop_event.set() 

            if self.detection_thread and self.detection_thread.is_alive():
                self.detection_thread.join(timeout=2.0) 
            if self.session_timer_thread and self.session_timer_thread.is_alive():
                 self.session_timer_thread.join(timeout=1.0)

            final_session_time_str = self.get_formatted_session_time()
            if self.session_start_time:
                 self.saved_session_seconds += (datetime.now() - self.session_start_time).total_seconds()
                 self.session_start_time = None 

            self._send_status_webhook(f"MultiScope Stopped (Session: {final_session_time_str})", 0xFF0000)

            self.gui_manager.update_status("Stopped", "red")
            self.gui_manager.update_detection_buttons()
            if self.gui_manager.root: self.gui_manager.root.title(f"MultiScope | v{self.version}")

            self.save_state()
            self.append_log("Detection stopped.")

        except Exception as e:
             error_logging(e, "Error stopping detection")

             self.gui_manager.update_status("Error Stopping", "red")
             self.gui_manager.update_detection_buttons()
             if self.gui_manager.root: self.gui_manager.root.title(f"MultiScope | v{self.version} (Error)")

    def _detection_loop(self):
        """The main background loop for running detection checks."""
        self.append_log("Detection loop started.")
        while not self.stop_event.is_set():
            try:

                self.detection_manager.check_all_accounts_biomes()

                if self.config_changed:
                     self.save_state(periodic=True)
                     self.config_changed = False 

                time.sleep(1.0) 

            except Exception as e:
                 error_logging(e, "Error in detection loop cycle")
                 time.sleep(5) 

        self.append_log("Detection loop finished.")

    def _update_session_timer_loop(self):
         """Background loop to update the session timer display periodically."""
         while not self.session_timer_stop_event.is_set():
             try:
                 if self.detection_running:
                     self.gui_manager.update_session_timer_display()
                 time.sleep(1.0) 
             except Exception as e:

                 time.sleep(5)

    def get_formatted_session_time(self):
         """Calculates and formats the total session time."""
         current_session_seconds = 0
         if self.detection_running and self.session_start_time:
             current_session_seconds = (datetime.now() - self.session_start_time).total_seconds()
         total_seconds = self.saved_session_seconds + current_session_seconds
         return format_session_time(total_seconds)

    def save_state(self, periodic=False):
        """Saves the application state (config, logs)."""
        if not periodic: 
             print("Saving application state...")
        else: 
             if not self.config_changed: return 

        self.config["biome_counts"] = self.biome_counts
        self.config["session_time"] = self.get_formatted_session_time() 
        self.config["accounts"] = self.accounts

        if hasattr(self.gui_manager, 'get_webhook_configs_for_save'):
            self.config["webhooks"] = self.gui_manager.get_webhook_configs_for_save()

        self.config["selected_theme"] = self.config.get("selected_theme", "darkly")
        self.config["dont_ask_for_update"] = self.config.get("dont_ask_for_update", False)
        self.config["biome_notification_enabled"] = self.config.get("biome_notification_enabled", {})
        self.config["biome_notifier"] = self.config.get("biome_notifier", {})

        if self.has_antiafk and self.antiafk:
             try:

                  if hasattr(self.antiafk, 'update_config'):
                      self.antiafk.update_config()
                  elif hasattr(self.antiafk, 'save_config'): 
                      self.antiafk.save_config()
                  else:
                      self.append_log("WARNING: AntiAFK object has no update_config or save_config method.")
             except Exception as e:
                  error_logging(e, "Error saving AntiAFK configuration")

        save_config(self.config)
        if not periodic: save_logs(self.logs)
        self.config_changed = False 
        if not periodic: print("Application state saved.")

    def on_close(self):
        """Handles application close event."""
        print("Close event received.")
        if self.detection_running:
            self.stop_detection() 
        else:

             self.save_state()

        try:
            keyboard.unhook_all()
            print("Global hotkeys unhooked.")
        except Exception as e:
            error_logging(e, "Error unhooking keyboard hotkeys")

        if self.has_antiafk and self.antiafk and hasattr(self.antiafk, 'shutdown'):
             try:
                 print("Shutting down AntiAFK system...")
                 self.antiafk.shutdown()
             except Exception as e:
                  error_logging(e, "Error during AntiAFK shutdown")

        print("Exiting MultiScope.")
        if self.gui_manager and self.gui_manager.root:
            self.gui_manager.root.destroy() 
        sys.exit() 

    def append_log(self, message):
        """Appends a message to the application logs and optionally updates the GUI."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_entry = {"timestamp": timestamp, "message": message}
        self.logs.append(log_entry)

        max_mem_logs = 5000
        if len(self.logs) > max_mem_logs:
             self.logs = self.logs[-max_mem_logs:]

        important_keywords = ["ERROR", "WARNING", "FATAL", "Starting detection", "Stopping detection", "Biome change", "PLAYER DETECTED", "Update found", "Webhook sent"]
        if any(keyword in message for keyword in important_keywords):
             print(f"[{timestamp}] {message}")

        if hasattr(self.gui_manager, 'logs_text') and self.gui_manager.logs_text:

            try:
                self.gui_manager.root.after(0, self.gui_manager.append_log_display, log_entry)
            except tk.TclError: 
                 pass
            except Exception as e:
                 print(f"Error updating GUI log: {e}") 

    def check_for_updates_on_startup(self):
        """Checks for updates after the GUI has loaded."""
        if self.config.get("dont_ask_for_update", False):
            self.append_log("Update check skipped (disabled in config).")
            return

        self.append_log("Checking for updates...")
        try:
            release_info = check_for_updates(self.version)
            if release_info:
                latest_version = release_info['parsed_tag_name'] 
                update_message = f"New update available: {latest_version}\n\nRelease Notes:\n{release_info.get('body', 'N/A')[:500]}...\n\nDo you want to download it now?"

                if self.gui_manager.ask_yes_no("Update Available!", update_message):

                    asset_url = None
                    assets = release_info.get('assets', [])
                    for asset in assets:
                        if asset.get('browser_download_url', '').endswith('.exe'):
                            asset_url = asset['browser_download_url']
                            break
                    if not asset_url and assets: 
                        asset_url = assets[0].get('browser_download_url')

                    if asset_url:
                        self.append_log(f"Downloading update from: {asset_url}")
                        save_path = download_update(asset_url, self.gui_manager.root)
                        if save_path:
                             if self.gui_manager.ask_yes_no("Download Complete", f"Update downloaded to:\\n{save_path}\\n\\nRun the new version now? (This will close the current app)"):
                                 try:
                                     os.startfile(save_path) 
                                     self.on_close() 
                                 except Exception as e:
                                     error_logging(e, f"Failed to start downloaded update at {save_path}")
                                     self.gui_manager.show_message_box("Error", f"Could not start the update automatically. Please run it manually from:\\n{save_path}", "error")
                    else:
                        self.gui_manager.show_message_box("No Download Link", "Could not find a download link for the update asset.", "warning")
                else:

                    if self.gui_manager.ask_yes_no("Skip Update", "Do you want to disable future update checks?"):
                        self.config["dont_ask_for_update"] = True
                        self.config_changed = True 
                        self.append_log("Update checks disabled by user.")
            else:
                 self.append_log("MultiScope is up to date.")
        except Exception as e:
            error_logging(e, "Failed during startup update check")

    def _send_status_webhook(self, status_message, color):
        """Sends a status update embed to configured webhooks."""
        webhooks_config = self.config.get("webhooks", [])
        if not webhooks_config: return

        timestamp_unix = int(time.time())
        icon_url = "https://i.postimg.cc/mDzwFfX1/GLITCHED.png"
        title = f"📊 Status Update: {status_message.split(' (')[0]}" 

        description = f"**Status:** {status_message}\n"
        description += f"**Time:** <t:{timestamp_unix}:F> (<t:{timestamp_unix}:R>)\n"
        description += f"**Version:** {self.version}\n"
        description += f"**Support Server:** https://discord.gg/6cuCu6ymkX"

        embed = {
            "title": title,
            "description": description,
            "color": color,
            "footer": {"text": f"MultiScope Status", "icon_url": icon_url},

        }

        active_accounts_str = ", ".join(sorted(list(self.active_accounts))) or "None"
        total_accounts = len(self.accounts)
        embed["fields"] = [
             {"name": "Total Accounts Configured", "value": str(total_accounts), "inline": True},
             {"name": "Active Accounts Monitored", "value": str(len(self.active_accounts)), "inline": True},

        ]

        for webhook_entry in webhooks_config:
             webhook_url = webhook_entry.get("url", "").strip()
             if not webhook_url: continue
             try:
                 response = requests.post(
                     webhook_url,
                     json={"embeds": [embed]},
                     headers={"Content-Type": "application/json"},
                     timeout=5 
                 )
                 response.raise_for_status()

             except Exception as e:
                  error_logging(e, f"Failed to send status webhook to ...{webhook_url[-10:]}")

    def get_ps_link_for_user(self, username):
         """Wrapper to use the utility function with the app's account list."""

         return get_ps_link_for_user(username, self.accounts, self.config.get("private_server_link", ""))

    def reinitialize_detection_states(self):
         """Calls the detection manager's reinitialization."""
         self.detection_manager.reset_detection_states()
         self.append_log("Reinitialized detection states after account changes.")