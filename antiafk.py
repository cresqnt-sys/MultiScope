import os
import time
import json
import ctypes
import psutil
import threading
import win32gui
import win32process
import win32con
import win32api
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
            self.config['antiafk_interval'] = 120  
        if 'antiafk_action' not in self.config:
            self.config['antiafk_action'] = 'space'
        if 'antiafk_user_safe' not in self.config:
            self.config['antiafk_user_safe'] = False
        if 'antiafk_dev_mode' not in self.config:
            self.config['antiafk_dev_mode'] = False
        if 'antiafk_sequential_mode' not in self.config:
            self.config['antiafk_sequential_mode'] = False
        if 'antiafk_sequential_delay' not in self.config:
            self.config['antiafk_sequential_delay'] = 0.75

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

        self.interval_var = tk.StringVar(value=str(self.config.get("antiafk_interval", 120)))  
        self.interval_entry = ttk.Entry(
            interval_frame,
            textvariable=self.interval_var,
            width=8
        )
        self.interval_entry.pack(side=tk.LEFT)

        for interval, label in [(120, "2m"), (300, "5m"), (600, "10m")]:  
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

        self.sequential_mode_var = tk.BooleanVar(value=self.config.get("antiafk_sequential_mode", False))
        self.sequential_mode_cb = ttk.Checkbutton(
            controls_frame, 
            text="Sequential Mode (Run actions in groups when running 5+ instances | HIGHLY RECOMMENDED WITH 10+ ACCOUNTS)", 
            variable=self.sequential_mode_var,
            command=self.update_config
        )
        self.sequential_mode_cb.grid(row=4, column=0, columnspan=2, sticky="w", padx=5, pady=5)

        sequential_delay_frame = ttk.Frame(controls_frame)
        sequential_delay_frame.grid(row=5, column=0, columnspan=2, sticky="w", padx=25, pady=2)

        ttk.Label(sequential_delay_frame, text="Delay between actions (seconds):").pack(side=tk.LEFT, padx=5)

        self.sequential_delay_var = tk.StringVar(value=str(self.config.get("antiafk_sequential_delay", 0.75)))
        self.sequential_delay_entry = ttk.Entry(
            sequential_delay_frame,
            textvariable=self.sequential_delay_var,
            width=5
        )
        self.sequential_delay_entry.pack(side=tk.LEFT, padx=5)
        self.sequential_delay_entry.bind("<FocusOut>", self.validate_sequential_delay)

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
            "The default interval is set to 2 minutes for optimal anti-AFK performance.\n\n"
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

            if hasattr(self, 'sequential_mode_var'):
                self.config['antiafk_sequential_mode'] = self.sequential_mode_var.get()

            if hasattr(self, 'sequential_delay_var'):
                try:
                    delay = float(self.sequential_delay_var.get())
                    if delay < 0.1:
                        delay = 0.1
                    elif delay > 5.0:
                        delay = 5.0
                    self.config['antiafk_sequential_delay'] = delay
                    self.sequential_delay_var.set(str(delay))
                except ValueError:
                    self.config['antiafk_sequential_delay'] = 0.75
                    self.sequential_delay_var.set("0.75")

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

        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            formatted_message = f"[{timestamp}] {message}\n"

            self.status_text.config(state="normal")
            self.status_text.insert("end", formatted_message)
            self.status_text.see("end")
            self.status_text.config(state="disabled")

            if hasattr(self.parent, 'append_log'):
                self.parent.append_log(f"[Anti-AFK] {message}")
        except (tk.TclError, RuntimeError, AttributeError):

            pass

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
        """Find all Roblox windows, including hidden ones if specified"""
        roblox_windows = []

        def enum_window_callback(hwnd, windows):
            try:

                if include_hidden or win32gui.IsWindowVisible(hwnd):
                    _, process_id = win32process.GetWindowThreadProcessId(hwnd)
                    process = psutil.Process(process_id)
                    if process.name().lower() == "robloxplayerbeta.exe":
                        title = win32gui.GetWindowText(hwnd)

                        if title and "Roblox" in title and not any(x in title for x in ["MSCTFIME", "Default IME", "NVIDIA"]):
                            windows.append(hwnd)
            except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
                pass
            return True

        win32gui.EnumWindows(enum_window_callback, roblox_windows)
        return roblox_windows

    def show_roblox_windows(self):
        """Show all Roblox windows, similar to original code"""

        windows = self.find_roblox_windows(include_hidden=True)

        if not windows:
            self.update_status("No Roblox windows found")
            return

        visible_count = 0
        for window in windows:

            if not win32gui.IsWindowVisible(window) or win32gui.IsIconic(window):

                if win32gui.IsIconic(window):
                    win32gui.ShowWindow(window, win32con.SW_RESTORE)
                win32gui.ShowWindow(window, win32con.SW_SHOW)
                win32gui.SetForegroundWindow(window)
                visible_count += 1

        self.update_status(f"Showed {visible_count} Roblox window(s)")

    def hide_roblox_windows(self):
        """Hide all Roblox windows, similar to original code"""
        windows = self.find_roblox_windows(include_hidden=False)

        if not windows:
            self.update_status("No visible Roblox windows found")
            return

        for window in windows:

            win32gui.ShowWindow(window, win32con.SW_HIDE)

        self.update_status(f"Hid {len(windows)} Roblox window(s)")

    def perform_antiafk_action(self, hwnd, action_type=None):
        """Perform an anti-AFK action on a specified window using direct Win32 API exactly like the C++ implementation"""
        if action_type is None:
            action_type = self.config.get('antiafk_action', 'space')

        if not win32gui.IsWindow(hwnd):
            self.update_status(f"Window {hwnd} is not a valid window")
            return False

        window_title = win32gui.GetWindowText(hwnd)
        if not window_title or "Roblox" not in window_title or any(x in window_title for x in ["MSCTFIME", "Default IME"]):
            self.update_status(f"Window '{window_title}' is not a valid Roblox window")
            return False

        old_hwnd = win32gui.GetForegroundWindow()
        was_minimized = win32gui.IsIconic(hwnd)

        try:

            ACTION_DELAY = 30  
            ALT_DELAY = 15     

            if was_minimized:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)

            win32gui.SetForegroundWindow(hwnd)

            def map_virtual_key(vk_code):

                return ctypes.windll.user32.MapVirtualKeyW(vk_code, 0)

            time.sleep(ACTION_DELAY / 1000.0)

            if action_type == 'space':

                vk_code = 0x20  
                scan_code = map_virtual_key(vk_code)
                ctypes.windll.user32.keybd_event(vk_code, scan_code, 0, 0)
                time.sleep(ALT_DELAY / 1000.0)
                ctypes.windll.user32.keybd_event(vk_code, scan_code, win32con.KEYEVENTF_KEYUP, 0)

            elif action_type == 'ws':

                vk_code_w = ord('W')  
                scan_code_w = map_virtual_key(vk_code_w)
                ctypes.windll.user32.keybd_event(vk_code_w, scan_code_w, 0, 0)
                time.sleep(ALT_DELAY / 1000.0)
                ctypes.windll.user32.keybd_event(vk_code_w, scan_code_w, win32con.KEYEVENTF_KEYUP, 0)
                time.sleep(ALT_DELAY / 1000.0)

                vk_code_s = ord('S')  
                scan_code_s = map_virtual_key(vk_code_s)
                ctypes.windll.user32.keybd_event(vk_code_s, scan_code_s, 0, 0)
                time.sleep(ALT_DELAY / 1000.0)
                ctypes.windll.user32.keybd_event(vk_code_s, scan_code_s, win32con.KEYEVENTF_KEYUP, 0)

            elif action_type == 'zoom':

                vk_code_i = ord('I')  
                scan_code_i = map_virtual_key(vk_code_i)
                ctypes.windll.user32.keybd_event(vk_code_i, scan_code_i, 0, 0)
                time.sleep(ALT_DELAY / 1000.0)
                ctypes.windll.user32.keybd_event(vk_code_i, scan_code_i, win32con.KEYEVENTF_KEYUP, 0)
                time.sleep(ALT_DELAY / 1000.0)

                vk_code_o = ord('O')  
                scan_code_o = map_virtual_key(vk_code_o)
                ctypes.windll.user32.keybd_event(vk_code_o, scan_code_o, 0, 0)
                time.sleep(ALT_DELAY / 1000.0)
                ctypes.windll.user32.keybd_event(vk_code_o, scan_code_o, win32con.KEYEVENTF_KEYUP, 0)

            time.sleep(ACTION_DELAY / 1000.0)

            if was_minimized:
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)

            if old_hwnd and old_hwnd != hwnd and win32gui.IsWindow(old_hwnd):

                if win32gui.IsWindowVisible(old_hwnd) and not win32gui.IsIconic(old_hwnd):

                    try:
                        class_name = win32gui.GetClassName(old_hwnd)
                        if class_name == "AntiAFK-RBX-tray":
                            return True
                    except:
                        pass

                    win32gui.ShowWindow(old_hwnd, win32con.SW_SHOW)
                    win32gui.SetWindowPos(old_hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, 
                                         win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)

                    current_thread = win32api.GetCurrentThreadId()
                    foreground_thread = win32process.GetWindowThreadProcessId(old_hwnd)[0]
                    ctypes.windll.user32.AttachThreadInput(current_thread, foreground_thread, True)

                    win32gui.BringWindowToTop(old_hwnd)
                    win32gui.SetForegroundWindow(old_hwnd)

                    ctypes.windll.user32.AttachThreadInput(current_thread, foreground_thread, False)

                    win32gui.SetWindowPos(old_hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                                        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)

            return True

        except Exception as e:
            self.log_error(e, f"Error performing anti-AFK action on '{window_title}'")

            try:
                if was_minimized:
                    win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
                if old_hwnd and win32gui.IsWindow(old_hwnd):
                    win32gui.SetForegroundWindow(old_hwnd)
            except Exception as restore_error:
                self.log_error(restore_error, "Error restoring window state after action failure")

            return False

    def test_action(self):
        """Test the Anti-AFK action on detected Roblox windows with improved feedback"""
        windows = self.find_roblox_windows(include_hidden=True)

        if not windows:
            self.update_status("No Roblox windows found for testing")
            return

        action_type = self.action_type_var.get()
        self.update_status(f"Testing {action_type} action on {len(windows)} Roblox window(s)...")

        old_hwnd = win32gui.GetForegroundWindow()

        for i, window in enumerate(windows):
            try:

                title = win32gui.GetWindowText(window)
                self.update_status(f"Testing on window: '{title}' (handle: {window})")

                for j in range(3):
                    self.update_status(f"Action attempt {j+1}/3...")
                    if not self.perform_antiafk_action(window, action_type):
                        self.update_status("Action failed, aborting remaining attempts")
                        break
                    time.sleep(0.5)  
            except Exception as e:
                self.log_error(e, f"Error testing anti-AFK action on window {window}")

        if old_hwnd and win32gui.IsWindow(old_hwnd):
            win32gui.SetForegroundWindow(old_hwnd)

        self.update_status(f"Completed testing {action_type} action on all windows")

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
        """Main Anti-AFK loop with improved True-AFK mode handling"""
        try:
            self.update_status("Anti-AFK loop started")

            interval = int(self.config.get('antiafk_interval', 120))  
            action_type = self.config.get('antiafk_action', 'space')
            user_safe = self.config.get('antiafk_user_safe', False)
            sequential_mode = self.config.get('antiafk_sequential_mode', False)
            sequential_delay = float(self.config.get('antiafk_sequential_delay', 0.75))

            MAX_WAIT_TIME = 1140  
            ACTIVITY_CHECK_INTERVAL = 1.0  

            self.update_status(f"Settings: Interval={interval}s, Action={action_type}, True-AFK={user_safe}, Sequential={sequential_mode}")
            if user_safe:
                self.update_status(f"True-AFK mode: Will wait for inactivity or max {MAX_WAIT_TIME//60} minutes since last action")

                self.user_active = False

            last_action_time = time.time() - interval + 10  
            last_status_update_time = 0

            while not self.antiafk_stop_event.is_set():
                try:
                    current_time = time.time()

                    roblox_windows = self.find_roblox_windows(include_hidden=True)

                    if not roblox_windows:

                        if current_time - last_status_update_time > 10:
                            self.update_status("No Roblox windows found, waiting...")
                            last_status_update_time = current_time

                        if self.antiafk_stop_event.wait(timeout=5):
                            break
                        continue

                    perform_action = False
                    elapsed_time = current_time - last_action_time

                    current_foreground = win32gui.GetForegroundWindow()

                    if user_safe and current_time - last_status_update_time > 30:

                        is_active = self.check_user_active()
                        if is_active:
                            inactive_time = 0
                            wait_time = MAX_WAIT_TIME - elapsed_time
                            self.update_status(f"User is active. Next action in {int(wait_time)}s max or when inactive.")
                        else:
                            inactive_time = (current_time - self.last_activity_time) 
                            self.update_status(f"User inactive for {int(inactive_time)}s. Action due in {max(0, int(interval - elapsed_time))}s.")
                        last_status_update_time = current_time

                    if user_safe:

                        is_active = elapsed_time % ACTIVITY_CHECK_INTERVAL < 0.1 and self.check_user_active()

                        if not is_active:
                            inactive_time = current_time - self.last_activity_time

                            if inactive_time >= 5 and elapsed_time >= interval:
                                self.update_status(f"User inactive for {int(inactive_time)}s and interval elapsed - performing action")
                                perform_action = True

                        if elapsed_time >= MAX_WAIT_TIME:
                            self.update_status(f"Maximum wait time reached ({MAX_WAIT_TIME//60} min since last action) - performing action")
                            perform_action = True
                    else:

                        if elapsed_time >= interval:
                            perform_action = True

                    if perform_action:
                        windows_count = len(roblox_windows)
                        use_sequential = sequential_mode and windows_count >= 5

                        if use_sequential:
                            self.update_status(f"Performing SEQUENTIAL Anti-AFK actions on {windows_count} Roblox window(s)")
                        else:
                            self.update_status(f"Performing Anti-AFK action on {windows_count} Roblox window(s)")

                        action_success = True
                        if self.config.get('multi_instance_enabled', False):

                            for i, window in enumerate(roblox_windows):
                                if not self.perform_antiafk_action(window, action_type):
                                    action_success = False

                                if use_sequential and i < len(roblox_windows) - 1:
                                    time.sleep(sequential_delay)
                        else:

                            if roblox_windows:
                                window = roblox_windows[0]
                                if not self.perform_antiafk_action(window, action_type):
                                    action_success = False

                        self.restore_foreground_window(current_foreground)

                        if action_success:
                            last_action_time = current_time
                            self.update_status("Anti-AFK action completed successfully")

                            time.sleep(0.5)
                        else:
                            self.update_status("Anti-AFK action failed, will retry on next cycle")

                    if self.antiafk_stop_event.wait(timeout=1.0):
                        break

                except Exception as e:
                    self.log_error(e, "Error in Anti-AFK action loop")
                    if self.antiafk_stop_event.wait(timeout=5):
                        break

            self.update_status("Anti-AFK loop ended")

        except Exception as e:
            self.log_error(e, "Error in Anti-AFK main loop")
            self.update_status(f"Critical error in Anti-AFK loop: {str(e)}")
        finally:
            self.antiafk_running = False

    def restore_foreground_window(self, hwnd):
        """Restore the foreground window using the approach from the original code"""
        if not hwnd or not win32gui.IsWindow(hwnd):
            return

        try:
            class_name = win32gui.GetClassName(hwnd)
            if class_name == "AntiAFK-RBX-tray":
                return
        except:
            pass

        if not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
            return

        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, 
                             win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)

        current_thread_id = win32api.GetCurrentThreadId()
        window_thread_id = win32process.GetWindowThreadProcessId(hwnd)[0]
        ctypes.windll.user32.AttachThreadInput(current_thread_id, window_thread_id, True)

        win32gui.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)

        ctypes.windll.user32.AttachThreadInput(current_thread_id, window_thread_id, False)

        win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0,
                             win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)

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
        """Thread function to monitor keyboard and mouse activity with improved reliability"""
        try:

            USER_INACTIVITY_WAIT = 5  
            MOUSE_POSITION_CHECK_INTERVAL = 0.5  

            self.user_active = False
            self.last_activity_time = time.time()
            self.update_status("User activity monitoring started - True-AFK mode active")

            last_mouse_pos = win32gui.GetCursorPos()
            last_pos_check_time = time.time()

            mouse_buttons = [0x01, 0x02, 0x04]  
            last_button_states = {button: False for button in mouse_buttons}
            last_activity_logged = 0
            last_inactivity_logged = 0

            while self.monitor_thread_running:
                activity = False
                current_time = time.time()

                for key in [0x08, 0x09, 0x0D, 0x10, 0x11, 0x12, 0x20, 0x25, 0x26, 0x27, 0x28]:  
                    if ctypes.windll.user32.GetAsyncKeyState(key) & 0x8000:
                        activity = True
                        break

                if not activity:

                    for i in range(65, 91):
                        if ctypes.windll.user32.GetAsyncKeyState(i) & 0x8000:
                            activity = True
                            break

                    if not activity:
                        for i in range(48, 58):
                            if ctypes.windll.user32.GetAsyncKeyState(i) & 0x8000:
                                activity = True
                                break

                if not activity:
                    for button in mouse_buttons:
                        button_state = ctypes.windll.user32.GetKeyState(button) & 0x8000
                        if button_state:
                            activity = True
                            last_button_states[button] = True
                            break
                        elif last_button_states[button]:
                            last_button_states[button] = False
                            activity = True
                            break

                if not activity and (current_time - last_pos_check_time) >= MOUSE_POSITION_CHECK_INTERVAL:
                    current_mouse_pos = win32gui.GetCursorPos()
                    if current_mouse_pos != last_mouse_pos:
                        activity = True
                    last_mouse_pos = current_mouse_pos
                    last_pos_check_time = current_time

                try:
                    current_foreground = win32gui.GetForegroundWindow()
                    if not hasattr(self, 'last_foreground_window'):
                        self.last_foreground_window = current_foreground
                    elif current_foreground != self.last_foreground_window:
                        activity = True
                        self.last_foreground_window = current_foreground
                except:
                    pass

                if activity:

                    self.last_activity_time = current_time

                    if not self.user_active and (current_time - last_activity_logged) > 10:
                        self.update_status("User activity detected")
                        last_activity_logged = current_time

                    self.user_active = True
                else:

                    inactivity_time = current_time - self.last_activity_time
                    if inactivity_time >= USER_INACTIVITY_WAIT:

                        if self.user_active and (current_time - last_inactivity_logged) > 10:
                            self.update_status(f"User inactive for {int(inactivity_time)} seconds")
                            last_inactivity_logged = current_time

                        self.user_active = False

                time.sleep(0.02)  

        except Exception as e:
            self.log_error(e, "Error in activity monitoring thread")
            self.monitor_thread_running = False

    def check_user_active(self):
        """Enhanced check if the user is currently active"""
        try:

            current_pos = win32gui.GetCursorPos()

            if hasattr(self, '_last_check_pos'):

                if current_pos != self._last_check_pos:
                    self._last_check_pos = current_pos
                    return True

            self._last_check_pos = current_pos

            game_keys = [
                0x20,  
                0x57,  
                0x41,  
                0x53,  
                0x44,  
                0x45,  
                0x52,  
                0x51,  
                0x46,  
                0x51,  
                0x31, 0x32, 0x33, 0x34, 0x35, 0x36,  
                0x10,  
                0x11,  
            ]

            for key in game_keys:
                if ctypes.windll.user32.GetAsyncKeyState(key) & 0x8000:
                    return True

            mouse_buttons = [0x01, 0x02, 0x04]  
            for button in mouse_buttons:
                if ctypes.windll.user32.GetKeyState(button) & 0x8000:
                    return True

            current_foreground = win32gui.GetForegroundWindow()
            if hasattr(self, '_last_check_foreground'):
                if current_foreground != self._last_check_foreground:
                    self._last_check_foreground = current_foreground
                    return True
            self._last_check_foreground = current_foreground

            return False
        except Exception as e:
            self.log_error(e, "Error checking user activity")

            return False

    def is_window_fullscreen(self, hwnd):
        """Check if a window is in fullscreen mode"""
        try:

            window_rect = win32gui.GetWindowRect(hwnd)
            monitor_info = win32api.GetMonitorInfo(win32api.MonitorFromWindow(hwnd))
            work_area = monitor_info.get("Work")
            monitor_area = monitor_info.get("Monitor")

            return window_rect == monitor_area and window_rect != work_area
        except Exception:
            return False

    def validate_sequential_delay(self, event=None):
        """Validate the sequential delay value"""
        try:
            value = self.sequential_delay_var.get().strip()
            delay = float(value)

            if delay < 0.1:
                delay = 0.1
            elif delay > 5.0:
                delay = 5.0

            self.sequential_delay_var.set(str(delay))
            self.update_config()
        except ValueError:
            self.sequential_delay_var.set("0.75")
            self.update_config()
            self.update_status("Invalid sequential delay value. Using default (0.75 seconds).")

    def test_action_with_delay(self):
        """Test the Anti-AFK action with more thorough diagnostic output"""
        self.update_status("Starting Anti-AFK test with detailed diagnostics...")

        all_windows = []

        def enum_window_callback(hwnd, result_list):
            if win32gui.IsWindow(hwnd):
                try:
                    title = win32gui.GetWindowText(hwnd)
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    process_name = ""
                    try:
                        process = psutil.Process(pid)
                        process_name = process.name()
                    except:
                        process_name = "unknown"

                    if title and "Roblox" in title:
                        result_list.append((hwnd, title, pid, process_name))
                except:
                    pass
            return True

        win32gui.EnumWindows(enum_window_callback, all_windows)

        if not all_windows:
            self.update_status("No windows with 'Roblox' in the title found!")
            return

        self.update_status(f"Found {len(all_windows)} windows with 'Roblox' in title:")
        for hwnd, title, pid, process_name in all_windows:
            self.update_status(f"Window: '{title}' (handle: {hwnd}, process: {process_name}, PID: {pid})")

        roblox_windows = []
        for hwnd, title, pid, process_name in all_windows:
            if process_name.lower() == "robloxplayerbeta.exe" and not any(x in title for x in ["MSCTFIME", "Default IME"]):
                roblox_windows.append(hwnd)

        if not roblox_windows:
            self.update_status("No main Roblox windows found after filtering!")
            return

        self.update_status(f"Testing with {len(roblox_windows)} main Roblox window(s) in 3 seconds...")

        self.test_btn.config(state="disabled")

        def run_test():
            action_type = self.action_type_var.get()
            old_hwnd = win32gui.GetForegroundWindow()

            for i, window in enumerate(roblox_windows):
                window_title = win32gui.GetWindowText(window)
                self.update_status(f"Testing on window {i+1}/{len(roblox_windows)}: '{window_title}'")

                self.update_status("===== DIRECT METHOD WITH MapVirtualKey =====")
                success1 = self.perform_antiafk_action(window, action_type)
                time.sleep(0.5)

                self.update_status("Test complete. Check if action was performed correctly.")

            if old_hwnd and win32gui.IsWindow(old_hwnd):
                win32gui.SetForegroundWindow(old_hwnd)

            self.test_btn.config(state="normal")

        self.status_text.after(3000, run_test)

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
            self.interval_var.set("120")  
            self.update_config()
            self.update_status("Invalid interval value. Using default (120 seconds).")

    def shutdown(self):
        """Safely shut down the Anti-AFK system - used when application is closing"""
        try:

            if self.antiafk_running:
                self.antiafk_stop_event.set()
                if self.antiafk_thread and self.antiafk_thread.is_alive():
                    self.antiafk_thread.join(timeout=1.0)
                self.antiafk_running = False

            if self.monitor_thread_running:
                self.monitor_thread_running = False
                if self.monitor_thread and self.monitor_thread.is_alive():
                    self.monitor_thread.join(timeout=1.0)
        except Exception:

            pass