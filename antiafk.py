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
        """Find all Roblox windows, including hidden ones if specified"""
        roblox_windows = []

        def enum_window_callback(hwnd, windows):
            try:
                # If include_hidden is True, check all windows regardless of visibility
                # If include_hidden is False, only check visible windows
                if include_hidden or win32gui.IsWindowVisible(hwnd):
                    _, process_id = win32process.GetWindowThreadProcessId(hwnd)
                    process = psutil.Process(process_id)
                    if process.name().lower() == "robloxplayerbeta.exe":
                        title = win32gui.GetWindowText(hwnd)
                        # Only include windows with "Roblox" in the title and exclude helper windows
                        if title and "Roblox" in title and not any(x in title for x in ["MSCTFIME", "Default IME", "NVIDIA"]):
                            windows.append(hwnd)
            except (psutil.NoSuchProcess, psutil.AccessDenied, Exception):
                pass
            return True

        win32gui.EnumWindows(enum_window_callback, roblox_windows)
        return roblox_windows

    def show_roblox_windows(self):
        """Show all Roblox windows, similar to original code"""
        # Find all Roblox windows, even hidden ones
        windows = self.find_roblox_windows(include_hidden=True)

        if not windows:
            self.update_status("No Roblox windows found")
            return
            
        visible_count = 0
        for window in windows:
            # Check if window is hidden or minimized
            if not win32gui.IsWindowVisible(window) or win32gui.IsIconic(window):
                # First restore, then show (similar to original code)
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
            # Hide the window while preserving its state
            win32gui.ShowWindow(window, win32con.SW_HIDE)

        self.update_status(f"Hid {len(windows)} Roblox window(s)")

    def perform_antiafk_action(self, hwnd, action_type=None):
        """Perform an anti-AFK action on a specified window using simple keybd_event approach"""
        if action_type is None:
            action_type = self.config.get('antiafk_action', 'space')
            
        # Verify the window is valid and actually a Roblox window
        if not win32gui.IsWindow(hwnd):
            self.update_status(f"Window {hwnd} is not a valid window")
            return False
            
        window_title = win32gui.GetWindowText(hwnd)
        if not window_title or "Roblox" not in window_title or any(x in window_title for x in ["MSCTFIME", "Default IME"]):
            self.update_status(f"Window '{window_title}' is not a valid Roblox window")
            return False

        # Store the original foreground window
        old_hwnd = win32gui.GetForegroundWindow()
        
        # Store original window state but don't change it automatically
        was_minimized = win32gui.IsIconic(hwnd)
        was_hidden = not win32gui.IsWindowVisible(hwnd)
        
        try:
            # Constants to match the original C++ code
            ACTION_DELAY = 30  # milliseconds 
            ALT_DELAY = 15     # milliseconds

            # Important: We're not forcing the window to be visible like we did before
            # This allows the anti-AFK to work even when windows are hidden
            
            # Make sure window is ready to receive input - without making it visible
            if was_minimized:
                # Just un-minimize without showing, if possible
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                if was_hidden:
                    # Re-hide if it was hidden
                    win32gui.ShowWindow(hwnd, win32con.SW_HIDE)
            
            # Set foreground window directly even if hidden - this works for sending keys
            win32gui.SetForegroundWindow(hwnd)
            
            # Sleep before action to match original code
            time.sleep(ACTION_DELAY / 1000.0)  # Convert ms to seconds
            
            # Perform the action using keybd_event directly
            if action_type == 'space':
                # Space key
                ctypes.windll.user32.keybd_event(0x20, ctypes.windll.user32.MapVirtualKeyW(0x20, 0), 0, 0)  # VK_SPACE press
                time.sleep(ALT_DELAY / 1000.0)  # ALT_DELAY ms
                ctypes.windll.user32.keybd_event(0x20, ctypes.windll.user32.MapVirtualKeyW(0x20, 0), 2, 0)  # VK_SPACE release with KEYEVENTF_KEYUP (2)
            
            elif action_type == 'ws':
                # W key
                ctypes.windll.user32.keybd_event(0x57, ctypes.windll.user32.MapVirtualKeyW(0x57, 0), 0, 0)  # W press
                time.sleep(ALT_DELAY / 1000.0)
                ctypes.windll.user32.keybd_event(0x57, ctypes.windll.user32.MapVirtualKeyW(0x57, 0), 2, 0)  # W release
                time.sleep(ALT_DELAY / 1000.0)
                # S key
                ctypes.windll.user32.keybd_event(0x53, ctypes.windll.user32.MapVirtualKeyW(0x53, 0), 0, 0)  # S press
                time.sleep(ALT_DELAY / 1000.0)
                ctypes.windll.user32.keybd_event(0x53, ctypes.windll.user32.MapVirtualKeyW(0x53, 0), 2, 0)  # S release
            
            elif action_type == 'zoom':
                # I key
                ctypes.windll.user32.keybd_event(0x49, ctypes.windll.user32.MapVirtualKeyW(0x49, 0), 0, 0)  # I press
                time.sleep(ALT_DELAY / 1000.0)
                ctypes.windll.user32.keybd_event(0x49, ctypes.windll.user32.MapVirtualKeyW(0x49, 0), 2, 0)  # I release
                time.sleep(ALT_DELAY / 1000.0)
                # O key
                ctypes.windll.user32.keybd_event(0x4F, ctypes.windll.user32.MapVirtualKeyW(0x4F, 0), 0, 0)  # O press
                time.sleep(ALT_DELAY / 1000.0)
                ctypes.windll.user32.keybd_event(0x4F, ctypes.windll.user32.MapVirtualKeyW(0x4F, 0), 2, 0)  # O release
            
            # Sleep after action to match original code
            time.sleep(ACTION_DELAY / 1000.0)
            
            # Restore window state if we changed it
            if was_minimized and not was_hidden:
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
            
            # Restore original foreground window
            if old_hwnd and old_hwnd != hwnd and win32gui.IsWindow(old_hwnd):
                # Use a more direct approach to restore focus
                current_thread_id = win32api.GetCurrentThreadId()
                other_thread_id = win32process.GetWindowThreadProcessId(old_hwnd)[0]
                ctypes.windll.user32.AttachThreadInput(current_thread_id, other_thread_id, True)
                win32gui.BringWindowToTop(old_hwnd)
                win32gui.SetForegroundWindow(old_hwnd)
                ctypes.windll.user32.AttachThreadInput(current_thread_id, other_thread_id, False)
                
                # Match original behavior by setting NOTOPMOST
                win32gui.SetWindowPos(old_hwnd, win32con.HWND_NOTOPMOST, 0, 0, 0, 0, 
                                     win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
            
            return True
            
        except Exception as e:
            self.log_error(e, f"Error performing anti-AFK action on '{window_title}'")
            # Try to restore window state even if action failed
            try:
                if was_minimized and not was_hidden:
                    win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
                if old_hwnd and win32gui.IsWindow(old_hwnd):
                    try:
                        win32gui.SetForegroundWindow(old_hwnd)
                    except:
                        pass
            except Exception as restore_error:
                self.log_error(restore_error, "Error restoring window state after action failure")
            return False

    def test_action(self):
        """Test the Anti-AFK action on detected Roblox windows"""
        windows = self.find_roblox_windows(include_hidden=True)

        if not windows:
            self.update_status("No Roblox windows found for testing")
            return

        action_type = self.action_type_var.get()
        self.update_status(f"Testing {action_type} action on {len(windows)} Roblox window(s)...")
        
        success_count = 0
        failure_count = 0
        skipped_count = 0
        
        # Collect all window handles to check, but filter them more stringently
        all_potential_windows = []
        
        def enum_window_callback(hwnd, result_list):
            try:
                if win32gui.IsWindow(hwnd) and win32gui.GetWindowText(hwnd):
                    _, process_id = win32process.GetWindowThreadProcessId(hwnd)
                    process = psutil.Process(process_id)
                    if process.name().lower() == "robloxplayerbeta.exe":
                        result_list.append(hwnd)
            except:
                pass
            return True
            
        win32gui.EnumWindows(enum_window_callback, all_potential_windows)
        
        self.update_status(f"Found {len(all_potential_windows)} total windows belonging to Roblox process")
        
        for window in all_potential_windows:
            try:
                # Get window title for better diagnostics
                title = win32gui.GetWindowText(window)
                
                # Check if this is a window we want to target
                if "Roblox" not in title or any(x in title for x in ["MSCTFIME", "Default IME", "NVIDIA"]):
                    self.update_status(f"Skipping window: '{title}' (not a main Roblox window)")
                    skipped_count += 1
                    continue
                    
                self.update_status(f"Testing on window: '{title}' (handle: {window})")
                
                if self.perform_antiafk_action(window, action_type):
                    success_count += 1
                else:
                    failure_count += 1
            except Exception as e:
                self.log_error(e, f"Error testing anti-AFK action on window {window}")
                failure_count += 1
        
        if success_count > 0 and failure_count == 0:
            self.update_status(f"Successfully tested {action_type} action on all {success_count} Roblox window(s)")
        elif success_count > 0:
            self.update_status(f"Partially successful: {action_type} action worked on {success_count} of {success_count + failure_count} windows")
        else:
            self.update_status(f"Failed to test {action_type} action on any windows")
            
        if skipped_count > 0:
            self.update_status(f"Skipped {skipped_count} non-Roblox windows belonging to the Roblox process")

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
            
            # Maximum wait time for True-AFK mode (19 minutes)
            MAX_WAIT_TIME = 1140  # seconds
            
            self.update_status(f"Settings: Interval={interval}s, Action={action_type}, True-AFK={user_safe}")
            if user_safe:
                self.update_status(f"True-AFK mode: Will wait for inactivity or max {MAX_WAIT_TIME//60} minutes from last action")
                # In True-AFK mode, we need to force a check of the activity state immediately
                self.user_active = True  # Assume active at start

            # Initial state setup
            last_user_active_state = True  # We start assuming the user is active
            last_action_time = time.time()
            action_overdue = False
            last_overdue_log_time = 0  # Track when we last logged an overdue message
            force_activity_check = True  # Force an immediate check of user activity status
            last_inactive_check_time = 0  # Track when we last checked inactive + overdue combo

            while not self.antiafk_stop_event.is_set():
                try:
                    # Get all windows belonging to Roblox process
                    roblox_windows = []
                    
                    def enum_window_callback(hwnd, result_list):
                        try:
                            if win32gui.IsWindow(hwnd):
                                _, process_id = win32process.GetWindowThreadProcessId(hwnd)
                                process = psutil.Process(process_id)
                                if process.name().lower() == "robloxplayerbeta.exe":
                                    title = win32gui.GetWindowText(hwnd)
                                    if "Roblox" in title and not any(x in title for x in ["MSCTFIME", "Default IME", "NVIDIA"]):
                                        result_list.append(hwnd)
                        except:
                            pass
                        return True
                        
                    win32gui.EnumWindows(enum_window_callback, roblox_windows)

                    if not roblox_windows:
                        self.update_status("No Roblox windows found, waiting...")
                        if self.antiafk_stop_event.wait(timeout=10):
                            break
                        continue

                    # Store the current foreground window for restoration later
                    current_foreground = win32gui.GetForegroundWindow()
                    
                    # Decide whether to perform action
                    current_time = time.time()
                    perform_action = False
                    elapsed_time = current_time - last_action_time

                    # Check if an action is overdue - but only log it occasionally to reduce spam
                    if elapsed_time >= interval:
                        if not action_overdue or (current_time - last_overdue_log_time) > 15:
                            self.update_status(f"Action is overdue (elapsed: {int(elapsed_time)}s, interval: {interval}s)")
                            last_overdue_log_time = current_time
                        action_overdue = True

                    if user_safe:
                        # User-safe mode logic
                        if force_activity_check:
                            # Reset the force flag
                            force_activity_check = False
                            
                            # Directly query the current activity state
                            is_active = self.check_user_active()
                            if not is_active and action_overdue:
                                self.update_status("Initial check: User is inactive AND action is overdue")
                                perform_action = True
                            last_user_active_state = is_active
                        # Main state transition check - active to inactive
                        elif last_user_active_state and not self.user_active and action_overdue:
                            self.update_status("User inactive detected AND action is overdue - performing action immediately")
                            perform_action = True
                        # Check inactive + overdue periodically even without state transition
                        elif not self.user_active and action_overdue:
                            # Check periodically if user is inactive and action is overdue
                            if current_time - last_inactive_check_time >= 5.0:  # Check every 5 seconds
                                self.update_status("User is inactive AND action is overdue - performing action")
                                perform_action = True
                                last_inactive_check_time = current_time
                        elif not self.user_active and not action_overdue:
                            # Only log this if it's been a while since the last action
                            if (current_time - last_action_time) > interval * 0.5:
                                self.update_status("User inactive detected but action is not due yet - waiting for interval")
                        # Or if max wait time has been reached (19 minutes)
                        elif elapsed_time >= MAX_WAIT_TIME:
                            perform_action = True
                            time_since_last = int(elapsed_time // 60)
                            self.update_status(f"Maximum wait time reached ({time_since_last} min), performing Anti-AFK action regardless of user activity")
                    else:
                        # Regular timer-based logic
                        if elapsed_time >= interval:
                            perform_action = True

                    if perform_action:
                        windows_count = len(roblox_windows)
                        self.update_status(f"Performing Anti-AFK action on {windows_count} Roblox window(s)")
                        
                        action_success = True
                        if self.config.get('multi_instance_enabled', False):
                            # Multi-instance mode - perform on all windows
                            for window in roblox_windows:
                                # Set foreground without forcing visibility
                                win32gui.SetForegroundWindow(window)
                                # Perform action just once
                                if not self.perform_antiafk_action(window, action_type):
                                    action_success = False
                        else:
                            # Single-instance mode - process only the first window
                            if roblox_windows:
                                window = roblox_windows[0]
                                win32gui.SetForegroundWindow(window)
                                if not self.perform_antiafk_action(window, action_type):
                                    action_success = False
                                    
                        # Restore the original foreground window
                        self.restore_foreground_window(current_foreground)
                        
                        # Reset tracking variables for next cycle
                        if action_success:
                            last_action_time = current_time
                            action_overdue = False
                            last_inactive_check_time = current_time
                            self.update_status("Anti-AFK action completed successfully")
                            
                            # After performing an action, we need to reset user activity tracking
                            # Wait a moment for any triggered activity to settle
                            time.sleep(0.5)
                            self.last_activity_time = current_time
                            # Force an immediate re-check of activity state on next cycle
                            force_activity_check = True
                        else:
                            self.update_status("Anti-AFK action failed, will retry on next cycle")

                    # Remember last activity state to detect transitions
                    last_user_active_state = self.user_active

                    # Wait for the specified interval before next check
                    # Use a shorter wait period to make stopping more responsive
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
            
    def restore_foreground_window(self, hwnd):
        """Restore the foreground window using the approach from the original code"""
        if not hwnd or not win32gui.IsWindow(hwnd):
            return
            
        # Check if it's our own window
        try:
            class_name = win32gui.GetClassName(hwnd)
            if class_name == "AntiAFK-RBX-tray":
                return
        except:
            pass
            
        # Check if window is visible and not minimized
        if not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
            return
            
        # Now restore focus using the same approach as the original
        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0, 
                             win32con.SWP_NOMOVE | win32con.SWP_NOSIZE)
                             
        # Attach thread input for more reliable focus switching
        current_thread_id = win32api.GetCurrentThreadId()
        window_thread_id = win32process.GetWindowThreadProcessId(hwnd)[0]
        ctypes.windll.user32.AttachThreadInput(current_thread_id, window_thread_id, True)
        
        win32gui.BringWindowToTop(hwnd)
        win32gui.SetForegroundWindow(hwnd)
        
        ctypes.windll.user32.AttachThreadInput(current_thread_id, window_thread_id, False)
        
        # Reset the window z-order
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
        """Thread function to monitor keyboard, mouse activity, and cursor movement"""
        try:
            # Constant matching the original code
            USER_INACTIVITY_WAIT = 3  # seconds

            # Initialize as active since the user just started the program
            self.user_active = True
            self.last_activity_time = time.time()
            self.update_status("User activity monitoring started - initially marked as active")

            # Track cursor position for movement detection
            last_cursor_pos = win32gui.GetCursorPos()
            last_activity_logged = 0  # To reduce log spam
            last_inactivity_logged = 0  # To reduce log spam

            while self.monitor_thread_running:
                activity = False

                # Check all keyboard keys (similar to original code)
                for i in range(1, 256):
                    # Use GetAsyncKeyState to match the original code's behavior
                    key_state = ctypes.windll.user32.GetAsyncKeyState(i)
                    if key_state & 0x8000:  # 0x8000 indicates key is pressed
                        activity = True
                        break

                # Check mouse buttons if no keyboard activity was detected
                if not activity:
                    mouse_buttons = [0x01, 0x02, 0x04]  # VK_LBUTTON, VK_RBUTTON, VK_MBUTTON
                    for button in mouse_buttons:
                        if ctypes.windll.user32.GetAsyncKeyState(button) & 0x8000:
                            activity = True
                            break

                # Check cursor movement if no key/button activity
                if not activity:
                    current_cursor_pos = win32gui.GetCursorPos()
                    # Check if cursor has moved more than 2 pixels in any direction
                    if (abs(current_cursor_pos[0] - last_cursor_pos[0]) > 2 or 
                        abs(current_cursor_pos[1] - last_cursor_pos[1]) > 2):
                        activity = True
                    last_cursor_pos = current_cursor_pos

                current_time = time.time()
                
                if activity:
                    # Update the last activity time
                    self.last_activity_time = current_time
                    
                    # Only log activity change if user was previously inactive
                    # and we haven't logged activity recently
                    if not self.user_active and (current_time - last_activity_logged) > 5:
                        self.update_status("User activity detected")
                        last_activity_logged = current_time
                    
                    self.user_active = True
                else:
                    # Check if user has been inactive long enough
                    if (current_time - self.last_activity_time) >= USER_INACTIVITY_WAIT:
                        # Only log inactivity if user was previously active
                        # and we haven't logged inactivity recently
                        if self.user_active and (current_time - last_inactivity_logged) > 5:
                            self.update_status(f"User inactive for {USER_INACTIVITY_WAIT} seconds")
                            last_inactivity_logged = current_time
                        
                        self.user_active = False

                time.sleep(0.1)  # 100ms sleep as in original code

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
        """Test Anti-AFK action after a 3-second delay with enhanced feedback"""
        # Get all windows belonging to Roblox process
        all_potential_windows = []
        
        def enum_window_callback(hwnd, result_list):
            try:
                if win32gui.IsWindow(hwnd) and win32gui.GetWindowText(hwnd):
                    _, process_id = win32process.GetWindowThreadProcessId(hwnd)
                    process = psutil.Process(process_id)
                    if process.name().lower() == "robloxplayerbeta.exe":
                        result_list.append(hwnd)
            except:
                pass
            return True
            
        win32gui.EnumWindows(enum_window_callback, all_potential_windows)
        
        # Filter to just the main Roblox windows
        roblox_windows = []
        for window in all_potential_windows:
            try:
                title = win32gui.GetWindowText(window)
                if "Roblox" in title and not any(x in title for x in ["MSCTFIME", "Default IME", "NVIDIA"]):
                    roblox_windows.append(window)
            except:
                pass
        
        if not roblox_windows:
            self.update_status("No main Roblox windows found for testing")
            return
            
        window_titles = []
        for window in roblox_windows:
            try:
                title = win32gui.GetWindowText(window)
                window_titles.append(f"'{title}'")
            except:
                window_titles.append(f"[Window {window}]")
                
        window_list = ", ".join(window_titles)
        
        self.update_status(f"Found {len(roblox_windows)} main Roblox window(s): {window_list}")
        if len(all_potential_windows) > len(roblox_windows):
            skipped = len(all_potential_windows) - len(roblox_windows)
            self.update_status(f"Filtered out {skipped} helper/IME windows")
            
        self.update_status(f"Testing Anti-AFK action ({self.action_type_var.get()}) in 3 seconds...")
        
        # Disable the test button temporarily to prevent multiple clicks
        self.test_btn.config(state="disabled")
        
        # Enable the button after the test completes
        def enable_test_button():
            self.test_btn.config(state="normal")
            
        self.status_text.after(3000, self.test_action)
        self.status_text.after(5000, enable_test_button)

    def check_user_active(self):
        """Directly check if the user is currently active by checking keyboard, mouse, and cursor"""
        try:
            # Check keyboard keys
            for i in range(1, 256):
                key_state = ctypes.windll.user32.GetAsyncKeyState(i)
                if key_state & 0x8000:  # Key is pressed
                    return True
                    
            # Check mouse buttons
            mouse_buttons = [0x01, 0x02, 0x04]  # VK_LBUTTON, VK_RBUTTON, VK_MBUTTON
            for button in mouse_buttons:
                if ctypes.windll.user32.GetAsyncKeyState(button) & 0x8000:
                    return True
                    
            # Get current cursor position for movement comparison
            # This is just a snapshot check - we don't track previous positions here
            # since this is called occasionally
            
            # No activity detected
            return False
        except Exception as e:
            self.log_error(e, "Error checking user activity")
            # Default to active in case of error (safer)
            return True