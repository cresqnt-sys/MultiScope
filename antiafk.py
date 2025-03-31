import os
import time
import json
import ctypes
import psutil
import threading
import win32gui
import win32process
import win32con
import keyboard
import tkinter as tk
from datetime import datetime
from tkinter import ttk

class AntiAFK:
    """Anti-AFK system for Roblox with multi-instance support"""

    def __init__(self, parent, config=None):
        """Initialize the Anti-AFK system

        Args:
            parent: The parent object for callbacks and error logging
            config: The configuration dictionary
        """
        self.parent = parent
        self.config = config or {}

        if 'antiafk_enabled' not in self.config:
            self.config['antiafk_enabled'] = False
        if 'multi_instance_enabled' not in self.config:
            self.config['multi_instance_enabled'] = False
        if 'antiafk_interval' not in self.config:
            self.config['antiafk_interval'] = 180  
        if 'antiafk_action' not in self.config:
            self.config['antiafk_action'] = 'space'
        if 'antiafk_user_safe' not in self.config:
            self.config['antiafk_user_safe'] = False
        if 'antiafk_dev_mode' not in self.config:
            self.config['antiafk_dev_mode'] = False

        self.antiafk_running = False
        self.antiafk_stop_event = threading.Event()
        self.antiafk_thread = None
        self.multi_instance_mutex = None

        self.user_active = False
        self.last_activity_time = 0
        self.monitor_thread = None
        self.monitor_thread_running = False

        if self.config.get('antiafk_user_safe', False):
            self.start_activity_monitor()

    def create_tab(self, notebook):
        """Create the Anti-AFK tab in the given notebook"""
        frame = ttk.Frame(notebook)
        notebook.add(frame, text='Anti-AFK')

        info_frame = ttk.LabelFrame(frame, text="Roblox Anti-AFK")
        info_frame.pack(fill=tk.X, padx=10, pady=10)

        description = ("Anti-AFK functionality keeps your Roblox windows active even when the window isn't focused.\n"
                      "This will work on all Roblox instances automatically.")
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

        self.multi_instance_var = tk.BooleanVar(value=True)

        ttk.Label(controls_frame, text="Action Interval (seconds):").grid(row=1, column=0, sticky="w", padx=5, pady=5)

        interval_frame = ttk.Frame(controls_frame)
        interval_frame.grid(row=1, column=1, sticky="w", padx=5, pady=5)

        self.interval_var = tk.StringVar(value=str(self.config.get("antiafk_interval", 180)))
        self.interval_entry = ttk.Entry(
            interval_frame,
            textvariable=self.interval_var,
            width=8
        )
        self.interval_entry.pack(side=tk.LEFT)

        for interval, label in [(180, "3m"), (360, "6m"), (540, "9m")]:
            btn = ttk.Button(
                interval_frame, 
                text=label, 
                width=4,
                command=lambda i=interval: self.set_interval(i)
            )
            btn.pack(side=tk.LEFT, padx=2)

        self.interval_entry.bind("<FocusOut>", self.validate_interval)

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
        self.action_combo.bind("<<ComboboxSelected>>", lambda e: self.update_config())

        self.user_safe_var = tk.BooleanVar(value=self.config.get("antiafk_user_safe", False))
        self.user_safe_cb = ttk.Checkbutton(
            controls_frame, 
            text="True-AFK Mode (Wait for inactivity before performing actions)", 
            variable=self.user_safe_var,
            command=self.update_config
        )
        self.user_safe_cb.grid(row=3, column=0, columnspan=2, sticky="w", padx=5, pady=5)

        status_frame = ttk.LabelFrame(frame, text="Status")
        status_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.status_text = tk.Text(status_frame, height=10, wrap="word", state="disabled")
        self.status_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        scrollbar = ttk.Scrollbar(self.status_text, orient="vertical", command=self.status_text.yview)
        scrollbar.pack(side="right", fill="y")
        self.status_text.config(yscrollcommand=scrollbar.set)

        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X, padx=10, pady=10)

        self.test_btn = ttk.Button(
            button_frame,
            text="Test Anti-AFK Action",
            command=self.test_action_with_delay,
            style="info.TButton"
        )
        self.test_btn.pack(side=tk.LEFT, padx=5, pady=5)

        self.show_btn = ttk.Button(
            button_frame,
            text="Show Roblox",
            command=self.show_roblox_windows,
            style="success.TButton"
        )
        self.show_btn.pack(side=tk.LEFT, padx=5, pady=5)

        self.hide_btn = ttk.Button(
            button_frame,
            text="Hide Roblox",
            command=self.hide_roblox_windows,
            style="danger.TButton"
        )
        self.hide_btn.pack(side=tk.LEFT, padx=5, pady=5)

        self.stop_btn = ttk.Button(
            button_frame,
            text="Stop Anti-AFK",
            command=lambda: self.toggle_antiafk(False),
            style="danger.TButton"
        )
        self.stop_btn.pack(side=tk.RIGHT, padx=5, pady=5)

        self.start_btn = ttk.Button(
            button_frame,
            text="Start Anti-AFK",
            command=lambda: self.toggle_antiafk(True),
            style="success.TButton"
        )
        self.start_btn.pack(side=tk.RIGHT, padx=5, pady=5)

        self.update_button_states()

        self.update_status("Anti-AFK tab initialized. Use the buttons above to control the functionality.")

        if hasattr(self.parent, 'config') and not self.parent.config.get('antiafk_first_launch_shown', False):

            if hasattr(self.parent, 'config'):
                self.parent.config['antiafk_first_launch_shown'] = True
                self.parent.save_config()
            self.show_first_launch_instructions()

        return frame

    def show_first_launch_instructions(self):
        """Show first launch instructions for Anti-AFK and multi-instance support"""
        instructions = (
            "Anti-AFK First Launch Instructions\n"
            "-----------------------------------\n"
            "1. IMPORTANT: Always open this macro BEFORE launching Roblox\n"
            "2. Anti-AFK keeps your Roblox character active by periodically sending key presses\n"
            "3. This will automatically work on all your Roblox instances\n"
            "4. True-AFK Mode waits for you to be inactive before performing actions. If you are active for too long you will be notified and an action will be performed regardless.\n\n"
            "To use:\n"
            "- Check 'Enable Anti-AFK' to start the anti-AFK functionality\n"
            "- Select an Action Type: Space (jump), W/S (movement), or Zoom (camera)\n"
            "- Use 'Show/Hide Roblox' buttons to manage window visibility, it will seem like roblox closed but it runs in the background (You can verify by checking your task manager)\n"
            "- The 'Test' button lets you verify the anti-AFK action works\n\n"
            "The default interval is set to 3 minutes for optimal anti-AFK performance.\n\n"
            "This message will only appear once."
        )

        popup = tk.Toplevel()
        popup.title("Anti-AFK First Launch Instructions")
        popup.geometry("600x400")
        popup.grab_set()  

        text = tk.Text(popup, wrap="word", padx=10, pady=10)
        text.pack(fill="both", expand=True)
        text.insert("1.0", instructions)
        text.config(state="disabled")

        ok_button = ttk.Button(popup, text="OK", command=popup.destroy)
        ok_button.pack(pady=10)

    def update_config(self):
        """Update configuration based on current UI settings"""
        try:

            self.config['antiafk_enabled'] = self.antiafk_enabled_var.get()
            self.config['multi_instance_enabled'] = self.multi_instance_var.get()
            self.config['antiafk_interval'] = int(self.interval_var.get())
            self.config['antiafk_action'] = self.action_type_var.get()
            self.config['antiafk_user_safe'] = self.user_safe_var.get()

            self.parent.save_config()

            self.update_button_states()

            if self.config['antiafk_user_safe']:
                self.start_activity_monitor()
            else:
                self.stop_activity_monitor()

            self.update_status(f"Configuration updated: Interval={self.config['antiafk_interval']}s, Action={self.config['antiafk_action']}")
        except Exception as e:
            self.log_error(e, "Error updating Anti-AFK configuration")

    def log_error(self, exception, message=None):
        """Log an error via the parent's error logging method"""
        if hasattr(self.parent, 'error_logging'):
            self.parent.error_logging(exception, message)
        self.update_status(f"Error: {message or str(exception)}")

    def update_button_states(self):
        """Update the state of control buttons based on current status"""

        antiafk_enabled = self.antiafk_enabled_var.get()

        self.start_btn.config(state="disabled" if antiafk_enabled else "normal")
        self.stop_btn.config(state="normal" if antiafk_enabled else "disabled")

        self.interval_entry.config(state="normal" if not antiafk_enabled else "disabled")
        self.action_combo.config(state="readonly" if not antiafk_enabled else "disabled")
        self.user_safe_cb.config(state="normal" if not antiafk_enabled else "disabled")

    def update_status(self, message):
        """Update the status text area with a new message"""
        if not hasattr(self, 'status_text'):
            return

        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}\n"

        self.status_text.config(state="normal")
        self.status_text.insert("end", formatted_message)
        self.status_text.see("end")
        self.status_text.config(state="disabled")

        if hasattr(self.parent, 'append_log'):
            self.parent.append_log(f"[Anti-AFK] {message}")

    def toggle_antiafk(self, enable=None):
        """Toggle the Anti-AFK functionality on or off"""
        if enable is None:
            enable = self.antiafk_enabled_var.get()
        else:
            self.antiafk_enabled_var.set(enable)

        self.config['antiafk_enabled'] = enable
        self.parent.save_config()

        if enable:

            if not self.antiafk_running:
                self.start_antiafk()
        else:

            if self.antiafk_running:
                self.stop_antiafk()

        self.update_button_states()

    def toggle_multi_instance(self):
        """Toggle multi-instance support"""
        enabled = self.multi_instance_var.get()
        self.config['multi_instance_enabled'] = enabled
        self.parent.save_config()

        if enabled:
            self.enable_multi_instance()
            self.update_status("Multi-instance support enabled")
        else:
            self.disable_multi_instance()
            self.update_status("Multi-instance support disabled")

    def enable_multi_instance(self):
        """Enable multi-instance support by creating a mutex"""
        try:

            if self.multi_instance_mutex:
                return True

            class SECURITY_ATTRIBUTES(ctypes.Structure):
                _fields_ = [
                    ("nLength", ctypes.c_ulong),
                    ("lpSecurityDescriptor", ctypes.c_void_p),
                    ("bInheritHandle", ctypes.c_int)
                ]

            security_attributes = SECURITY_ATTRIBUTES()
            security_attributes.nLength = ctypes.sizeof(security_attributes)
            security_attributes.lpSecurityDescriptor = None
            security_attributes.bInheritHandle = True

            self.multi_instance_mutex = ctypes.windll.kernel32.CreateMutexW(
                None, True, "ROBLOX_singletonEvent"
            )

            if self.multi_instance_mutex == 0:
                error = ctypes.windll.kernel32.GetLastError()
                if error == 6:  
                    self.update_status("Error 6: Invalid handle. Trying alternate method...")

                    self.multi_instance_mutex = ctypes.windll.kernel32.CreateMutexW(
                        ctypes.byref(security_attributes), True, "ROBLOX_singletonEvent"
                    )
                    if self.multi_instance_mutex == 0:

                        self.update_status("Still failed. Trying with alternate mutex name...")
                        self.multi_instance_mutex = ctypes.windll.kernel32.CreateMutexW(
                            None, True, "ROBLOX_singletonMutex"
                        )
                        if self.multi_instance_mutex == 0:
                            self.update_status(f"Still failed to create mutex: Error {ctypes.windll.kernel32.GetLastError()}")
                            self.multi_instance_var.set(False)
                            return False
                elif error == 183:  
                    self.update_status("Mutex already exists but is owned by another process")

                    self.multi_instance_mutex = ctypes.windll.kernel32.OpenMutexW(0x00100000, False, "ROBLOX_singletonEvent")
                    if self.multi_instance_mutex == 0:
                        self.update_status("Could not open existing mutex")
                        self.multi_instance_var.set(False)
                        return False
                else:
                    self.update_status(f"Failed to create mutex: Error {error}")
                    self.multi_instance_var.set(False)
                    return False

            self.update_status("Multi-instance mutex created successfully")
            return True
        except Exception as e:
            self.log_error(e, "Error enabling multi-instance support")
            self.update_status(f"Error enabling multi-instance support: {str(e)}")
            self.multi_instance_var.set(False)
            return False

    def disable_multi_instance(self):
        """Disable multi-instance support by releasing the mutex"""
        try:
            if self.multi_instance_mutex:
                ctypes.windll.kernel32.CloseHandle(self.multi_instance_mutex)
                self.multi_instance_mutex = None

            return True
        except Exception as e:
            self.log_error(e, "Error disabling multi-instance support")
            self.update_status(f"Error disabling multi-instance support: {str(e)}")
            return False

    def find_roblox_windows(self, include_hidden=True):
        """Find all Roblox windows, optionally including hidden ones"""
        roblox_windows = []

        def enum_window_callback(hwnd, windows):
            if win32gui.IsWindowVisible(hwnd) or include_hidden:
                if win32gui.GetWindowText(hwnd):
                    try:
                        _, process_id = win32process.GetWindowThreadProcessId(hwnd)
                        process = psutil.Process(process_id)
                        if process.name().lower() == "robloxplayerbeta.exe":
                            windows.append(hwnd)
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        pass
            return True

        win32gui.EnumWindows(enum_window_callback, roblox_windows)
        return roblox_windows

    def show_roblox_windows(self):
        """Show all Roblox windows"""
        windows = self.find_roblox_windows(include_hidden=True)

        if not windows:
            self.update_status("No Roblox windows found")
            return

        for window in windows:
            if not win32gui.IsWindowVisible(window) or win32gui.IsIconic(window):
                win32gui.ShowWindow(window, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(window)

        self.update_status(f"Showed {len(windows)} Roblox window(s)")

    def hide_roblox_windows(self):
        """Hide all Roblox windows"""
        windows = self.find_roblox_windows(include_hidden=False)

        if not windows:
            self.update_status("No visible Roblox windows found")
            return

        for window in windows:
            win32gui.ShowWindow(window, win32con.SW_HIDE)

        self.update_status(f"Hid {len(windows)} Roblox window(s)")

    def perform_antiafk_action(self, hwnd, action_type=None):
        """Perform an anti-AFK action on a specified window"""
        if action_type is None:
            action_type = self.config.get('antiafk_action', 'space')

        old_hwnd = win32gui.GetForegroundWindow()

        was_minimized = win32gui.IsIconic(hwnd)
        if was_minimized:
            win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.03)  

        if action_type == 'space':

            keyboard.press_and_release('space')
        elif action_type == 'ws':

            keyboard.press_and_release('w')
            time.sleep(0.015)
            keyboard.press_and_release('s')
        elif action_type == 'zoom':

            keyboard.press_and_release('i')
            time.sleep(0.015)
            keyboard.press_and_release('o')

        if was_minimized:
            win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)

        if old_hwnd and old_hwnd != hwnd and win32gui.IsWindow(old_hwnd):
            try:
                win32gui.SetForegroundWindow(old_hwnd)
            except:
                pass

        return True

    def test_action(self):
        """Test the Anti-AFK action on detected Roblox windows"""
        windows = self.find_roblox_windows(include_hidden=True)

        if not windows:
            self.update_status("No Roblox windows found for testing")
            return

        action_type = self.action_type_var.get()

        for window in windows:
            self.perform_antiafk_action(window, action_type)
        self.update_status(f"Tested {action_type} action on {len(windows)} Roblox window(s)")

    def start_antiafk(self):
        """Start the Anti-AFK functionality"""
        if self.antiafk_running:
            self.update_status("Anti-AFK is already running")
            return

        self.antiafk_stop_event.clear()

        self.antiafk_thread = threading.Thread(target=self.antiafk_loop, daemon=True)
        self.antiafk_thread.start()

        if self.config.get('antiafk_user_safe', False):
            self.start_activity_monitor()

        self.antiafk_running = True

        self.update_status("Anti-AFK started")
        self.update_button_states()

    def stop_antiafk(self):
        """Stop the Anti-AFK functionality"""
        if not self.antiafk_running:
            self.update_status("Anti-AFK is not running")
            return

        self.antiafk_stop_event.set()

        if self.antiafk_thread and self.antiafk_thread.is_alive():
            self.antiafk_thread.join(timeout=2.0)

        self.stop_activity_monitor()

        self.antiafk_running = False
        self.antiafk_thread = None

        self.update_status("Anti-AFK stopped")
        self.update_button_states()

    def antiafk_loop(self):
        """Main Anti-AFK loop that performs actions on Roblox windows"""
        try:
            self.update_status("Anti-AFK loop started")

            interval = int(self.config.get('antiafk_interval', 180))
            action_type = self.config.get('antiafk_action', 'space')
            user_safe = self.config.get('antiafk_user_safe', False)

            self.update_status(f"Settings: Interval={interval}s, Action={action_type}, True-AFK={user_safe}")

            last_user_active_state = self.user_active
            last_action_time = time.time()

            while not self.antiafk_stop_event.is_set():
                try:

                    windows = self.find_roblox_windows(include_hidden=True)

                    if not windows:
                        self.update_status("No Roblox windows found, waiting...")
                        if self.antiafk_stop_event.wait(timeout=10):
                            break
                        continue

                    current_time = time.time()
                    perform_action = False

                    if user_safe:

                        if last_user_active_state and not self.user_active:
                            self.update_status("User inactive detected, waiting 5 seconds to confirm...")

                            if self.antiafk_stop_event.wait(timeout=5.0):
                                break

                            if not self.user_active:
                                self.update_status("User inactivity confirmed, performing action immediately")
                                perform_action = True

                        elif (current_time - last_action_time) >= interval:
                            perform_action = True

                            if self.user_active:
                                self.update_status("Maximum interval reached, performing Anti-AFK action despite user activity")
                    else:

                        if (current_time - last_action_time) >= interval:
                            perform_action = True

                    if perform_action:

                        self.update_status(f"Performing Anti-AFK action on {len(windows)} Roblox window(s)")
                        for window in windows:
                            if self.antiafk_stop_event.is_set():
                                break
                            self.perform_antiafk_action(window, action_type)

                        last_action_time = current_time

                    last_user_active_state = self.user_active

                    if self.antiafk_stop_event.wait(timeout=1.0):
                        break

                except Exception as e:
                    self.log_error(e, "Error in Anti-AFK action loop")
                    self.update_status(f"Error performing Anti-AFK action: {str(e)}")
                    if self.antiafk_stop_event.wait(timeout=10):
                        break

            self.update_status("Anti-AFK loop ended")

        except Exception as e:
            self.log_error(e, "Error in Anti-AFK main loop")
            self.update_status(f"Critical error in Anti-AFK loop: {str(e)}")
        finally:
            self.antiafk_running = False

    def start_activity_monitor(self):
        """Start monitoring user keyboard/mouse activity for True-AFK Mode"""
        if self.monitor_thread_running:
            return

        self.monitor_thread_running = True
        self.last_activity_time = time.time()
        self.monitor_thread = threading.Thread(target=self.monitor_user_activity, daemon=True)
        self.monitor_thread.start()
        self.update_status("User activity monitoring started")

    def stop_activity_monitor(self):
        """Stop monitoring user activity"""
        if not self.monitor_thread_running:
            return

        self.monitor_thread_running = False
        if self.monitor_thread and self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2.0)
        self.monitor_thread = None
        self.update_status("User activity monitoring stopped")

    def monitor_user_activity(self):
        """Thread function to monitor keyboard and mouse activity"""
        try:
            user_inactivity_wait = 5  

            while self.monitor_thread_running:
                activity = False

                for key_code in range(1, 256):
                    if keyboard.is_pressed(key_code):
                        activity = True
                        break

                if activity:
                    self.last_activity_time = time.time()
                    self.user_active = True
                else:
                    current_time = time.time()
                    if (current_time - self.last_activity_time) >= user_inactivity_wait:
                        self.user_active = False

                time.sleep(0.1)

        except Exception as e:
            self.log_error(e, "Error in activity monitoring thread")
            self.monitor_thread_running = False

    def shutdown(self):
        """Clean up resources when shutting down"""

        if self.antiafk_running:
            self.stop_antiafk()

        self.disable_multi_instance()

        self.stop_activity_monitor()

    def set_interval(self, seconds):
        """Set the interval to a predefined value"""
        self.interval_var.set(str(seconds))
        self.update_config()

    def validate_interval(self, event=None):
        """Validate the interval value"""
        try:
            value = self.interval_var.get().strip()

            interval = int(value)

            if interval < 5:
                interval = 5
            elif interval > 3600:
                interval = 3600
            self.interval_var.set(str(interval))
            self.update_config()
        except ValueError:

            self.interval_var.set("180")
            self.update_config()
            self.update_status("Invalid interval value. Using default (180 seconds).")

    def test_action_with_delay(self):
        """Test Anti-AFK action after a 3-second delay"""
        self.update_status("Testing Anti-AFK action in 3 seconds...")

        self.status_text.after(3000, self.test_action)