import sys
import traceback
import os

import tkinter as tk
import ttkbootstrap as ttk
from tkinter import messagebox, filedialog
from PIL import Image, ImageTk 
import webbrowser
from datetime import datetime, timezone
import ctypes 

from utils import create_tooltip, error_logging 

APP_NAME = "MultiScope"
APP_VERSION = "0.9.8-Stable"
MYAPPID = f"{APP_NAME}.App.{APP_VERSION}"
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(MYAPPID)
except ImportError:
    print("ctypes not found, cannot set AppUserModelID.")
except AttributeError:
    print("Running on non-Windows OS or shell32 not available, cannot set AppUserModelID.")
except Exception as e:
     print(f"Error setting AppUserModelID: {e}")

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:

        base_path = sys._MEIPASS
    except Exception:

        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

class GuiManager:
    def __init__(self, app_instance):
        """Initialize the GUI Manager.

        Args:
            app_instance: The main application instance (MultiScopeApp).
        """
        self.app = app_instance
        self.root = None
        self.notebook = None
        self.status_label = None
        self.version_label = None
        self.start_detection_btn = None
        self.stop_detection_btn = None
        self.stats_labels = {}
        self.total_biomes_label = None
        self.session_label = None
        self.logs_text = None
        self.webhook_entries = []
        self.webhook_content_frame = None 
        self.antiafk = getattr(app_instance, 'antiafk', None)

    def setup_gui(self):
        """Sets up the main GUI window and elements."""
        selected_theme = self.app.config.get("selected_theme", "darkly")
        self.root = ttk.Window(themename=selected_theme)

        try:
            icon_path = resource_path('biomescope.ico')
            if os.path.exists(icon_path):
                self.root.iconbitmap(icon_path)
            else:
                 print(f"Error: Icon file not found at {icon_path}")
        except tk.TclError:
            print("Error: Could not load 'biomescope.ico' (TclError).")
        except Exception as e:
            print(f"An unexpected error occurred setting the icon: {e}")

        if self.app.myappid:
            try:
                 ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(self.app.myappid)
            except Exception as e:
                 print(f"Failed to set AppUserModelID or icon: {e}")

        self.root.title(f"MultiScope | Version {self.app.version}")
        self.root.geometry("735x530")
        self.root.resizable(True, True)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.root.protocol("WM_DELETE_WINDOW", self.app.on_close)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=5, pady=5)

        webhook_frame = ttk.Frame(self.notebook)
        stats_frame = ttk.Frame(self.notebook)
        credits_frame = ttk.Frame(self.notebook)
        merchant_frame = ttk.Frame(self.notebook)

        self.notebook.add(webhook_frame, text='Webhooks & Control')
        self.notebook.add(stats_frame, text='Stats & Logs')
        self.notebook.add(merchant_frame, text='Merchants')

        if self.app.has_antiafk and self.antiafk:
            try:
                antiafk_frame = self.antiafk.create_tab(self.notebook)
                if antiafk_frame:
                     self.notebook.add(antiafk_frame, text='Anti-AFK')
            except Exception as e:
                 log_func = getattr(self.app, 'error_logging', print)
                 log_func(e, "Failed to create Anti-AFK tab")

        self.notebook.add(credits_frame, text='Credits')

        self._create_webhook_tab(webhook_frame)
        self._create_stats_tab(stats_frame)
        self._create_credit_tab(credits_frame)
        self._create_merchant_tab(merchant_frame)

        self.status_frame = ttk.Frame(self.root)
        self.status_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=10, pady=5)
        self.status_label = ttk.Label(self.status_frame, text="Ready")
        self.status_label.pack(side=tk.LEFT)
        self.version_label = ttk.Label(self.status_frame, text=f"v{self.app.version}")
        self.version_label.pack(side=tk.RIGHT)

        self.update_detection_buttons()
        self.update_status("Ready", "grey")
        self.root.after(1500, self.app.check_for_updates_on_startup)

    def run(self):
        """Starts the Tkinter main loop."""
        if self.root:
            self.root.mainloop()

    def update_status(self, text, color="black"):
        """Updates the status bar label."""
        if self.status_label and self.status_label.winfo_exists():
            self.status_label.config(text=f"Status: {text}", foreground=color)

    def update_detection_buttons(self):
        """Updates the state of Start/Stop detection buttons based on app state."""
        is_running = self.app.detection_running
        if self.start_detection_btn and self.start_detection_btn.winfo_exists():
            self.start_detection_btn.configure(state="disabled" if is_running else "normal")
        if self.stop_detection_btn and self.stop_detection_btn.winfo_exists():
            self.stop_detection_btn.configure(state="normal" if is_running else "disabled")

    def _create_webhook_tab(self, parent_frame):
        """Creates the content for the Webhooks & Control tab."""
        master_frame = ttk.Frame(parent_frame)
        master_frame.pack(fill="both", expand=True)

        top_frame = ttk.Frame(master_frame)
        top_frame.pack(fill="x", side="top", padx=10, pady=5)
        ttk.Label(top_frame, text="Discord Webhooks", font=("Arial", 11, "bold")).pack(side="left", anchor='w', padx=5)
        ttk.Button(top_frame, text="Manage Accounts", command=self.open_accounts_manager, style="secondary.TButton", width=15).pack(side="right", padx=5)

        help_frame = ttk.Frame(master_frame)
        help_frame.pack(fill="x", side="top", padx=10, pady=5)
        ttk.Label(help_frame, text="Add Discord webhook URLs to receive notifications. Configure which accounts notify which webhooks.", wraplength=700).pack(fill='x', padx=5)

        button_frame = ttk.Frame(master_frame)
        button_frame.pack(fill="x", side="top", padx=10, pady=5)
        ttk.Button(button_frame, text="Add Webhook", command=lambda: self._add_webhook_entry(), style="info.TButton", width=15).pack(side="left", padx=5)

        center_frame = ttk.Frame(master_frame)
        center_frame.pack(fill="both", expand=True, side="top", padx=10, pady=5)
        canvas = tk.Canvas(center_frame, highlightthickness=0, bg=ttk.Style().lookup('TFrame', 'background'))
        scrollbar = ttk.Scrollbar(center_frame, orient="vertical", command=canvas.yview)
        self.webhook_content_frame = ttk.Frame(canvas)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas_frame_id = canvas.create_window((0, 0), window=self.webhook_content_frame, anchor="nw")

        def update_scroll_region(event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas_width = event.width if event else canvas.winfo_width()
            canvas.itemconfig(canvas_frame_id, width=canvas_width)
        self.webhook_content_frame.bind("<Configure>", update_scroll_region)
        canvas.bind("<Configure>", update_scroll_region)

        def _on_mousewheel(event):
            if event.delta: delta = -1 * (event.delta // 120)
            elif event.num == 5: delta = 1
            elif event.num == 4: delta = -1
            else: delta = 0
            canvas.yview_scroll(delta, "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)
        self.webhook_content_frame.bind("<MouseWheel>", _on_mousewheel)
        parent_frame.bind("<Unmap>", lambda e: canvas.unbind_all("<MouseWheel>"))
        parent_frame.bind("<Map>", lambda e: canvas.bind_all("<MouseWheel>", _on_mousewheel))

        bottom_frame = ttk.Frame(master_frame)
        bottom_frame.pack(fill="x", side="bottom", padx=10, pady=10)
        ttk.Button(bottom_frame, text="Configure Biomes", command=self.open_biome_notification_settings, style="info.TButton", width=15).pack(side="left", padx=5)
        self.stop_detection_btn = ttk.Button(bottom_frame, text="Stop (F2)", command=self.app.stop_detection, style="danger.TButton", width=12)
        self.stop_detection_btn.pack(side="right", padx=5)
        self.start_detection_btn = ttk.Button(bottom_frame, text="Start (F1)", command=self.app.start_detection, style="success.TButton", width=12)
        self.start_detection_btn.pack(side="right", padx=5)

        self.webhook_entries = []
        webhooks_from_config = self.app.config.get("webhooks", [])
        for webhook_config in webhooks_from_config:
            self._add_webhook_entry(webhook_config)

    def _add_webhook_entry(self, webhook_config=None):
        """Adds a single webhook entry UI to the webhook tab."""
        entry_idx = len(self.webhook_entries)
        webhook_data = {"config": webhook_config if webhook_config else {}}
        entry_frame = ttk.LabelFrame(self.webhook_content_frame, text=f"Webhook #{entry_idx + 1}")
        entry_frame.pack(fill='x', pady=8, padx=5)

        url_frame = ttk.Frame(entry_frame); url_frame.pack(fill='x', pady=5, padx=8)
        ttk.Label(url_frame, text="URL:", width=5).pack(side='left', padx=(0, 5))
        url_entry = ttk.Entry(url_frame, show="*"); url_entry.pack(side='left', fill='x', expand=True, padx=(0, 10))
        if webhook_config: url_entry.insert(0, webhook_config.get("url", ""))
        webhook_data["url_entry"] = url_entry

        button_frame = ttk.Frame(entry_frame); button_frame.pack(fill='x', pady=(0, 5), padx=8)
        test_btn = ttk.Button(button_frame, text="Test", command=lambda u=url_entry: self.app.detection_manager.test_webhook(u.get().strip()), style="info.TButton", width=8)
        test_btn.pack(side='left', padx=5); create_tooltip(test_btn, "Send a test message to this webhook URL")
        show_btn = ttk.Button(button_frame, text="Show", command=lambda: url_entry.configure(show=""), style="secondary.TButton", width=8); show_btn.pack(side='left', padx=5)
        hide_btn = ttk.Button(button_frame, text="Hide", command=lambda: url_entry.configure(show="*"), style="secondary.TButton", width=8); hide_btn.pack(side='left', padx=5)
        remove_btn = ttk.Button(button_frame, text="Remove", command=lambda data=webhook_data: self._remove_webhook_entry(data), style="danger.TButton", width=8); remove_btn.pack(side='right', padx=5)

        notify_frame = ttk.Frame(entry_frame); notify_frame.pack(fill='x', pady=(0, 5), padx=8)
        initial_notify_all = True; initial_account_list = []
        if webhook_config and "account_notifications" in webhook_config:
             if isinstance(webhook_config["account_notifications"], list) and webhook_config["account_notifications"]:
                 initial_notify_all = False; initial_account_list = webhook_config["account_notifications"]
        notify_all_var = tk.BooleanVar(value=initial_notify_all); webhook_data["notify_all_var"] = notify_all_var
        webhook_data["selected_accounts"] = initial_account_list if not initial_notify_all else []
        account_selection_frame = ttk.Frame(entry_frame); webhook_data["selection_frame"] = account_selection_frame
        all_accounts_check = ttk.Checkbutton(notify_frame, text="Notify for all configured accounts", variable=notify_all_var, command=lambda data=webhook_data: self._toggle_account_selection(data))
        all_accounts_check.pack(anchor='w')

        account_selection_frame.pack(fill='x', pady=(0, 5), padx=8)

        account_checklist_scroll_frame = ttk.Frame(account_selection_frame)
        checklist_canvas = tk.Canvas(account_checklist_scroll_frame, height=100, highlightthickness=0, bg=ttk.Style().lookup('TFrame', 'background'))
        checklist_scrollbar = ttk.Scrollbar(account_checklist_scroll_frame, orient="vertical", command=checklist_canvas.yview)
        checklist_canvas.configure(yscrollcommand=checklist_scrollbar.set)
        checklist_inner_frame = ttk.Frame(checklist_canvas)
        checklist_canvas.pack(side="left", fill="both", expand=True)
        checklist_scrollbar.pack(side="right", fill="y")
        checklist_canvas_frame_id = checklist_canvas.create_window((0, 0), window=checklist_inner_frame, anchor="nw")

        def _configure_checklist_scroll(event=None):
            checklist_canvas.configure(scrollregion=checklist_canvas.bbox("all"))
            canvas_width = event.width if event else checklist_canvas.winfo_width()
            checklist_canvas.itemconfig(checklist_canvas_frame_id, width=canvas_width)

        checklist_inner_frame.bind("<Configure>", _configure_checklist_scroll)
        checklist_canvas.bind("<Configure>", _configure_checklist_scroll)

        def _on_checklist_mousewheel(event):
            if event.delta: delta = -1 * (event.delta // 120)
            elif event.num == 5: delta = 1
            elif event.num == 4: delta = -1
            else: delta = 0
            checklist_canvas.yview_scroll(delta, "units")

        checklist_canvas.bind("<MouseWheel>", _on_checklist_mousewheel)
        checklist_inner_frame.bind("<MouseWheel>", _on_checklist_mousewheel)

        account_selection_frame.bind("<Map>", lambda e: checklist_canvas.bind_all("<MouseWheel>", _on_checklist_mousewheel))
        account_selection_frame.bind("<Unmap>", lambda e: checklist_canvas.unbind_all("<MouseWheel>"))

        webhook_data["checklist_frame"] = checklist_inner_frame
        webhook_data["checklist_scroll_frame"] = account_checklist_scroll_frame
        webhook_data["account_vars"] = {}
        self._populate_account_checklist(webhook_data)
        self._toggle_account_selection(webhook_data, initial_state=initial_notify_all)
        self.webhook_entries.append(webhook_data)
        return webhook_data

    def _populate_account_checklist(self, webhook_data):
        """Populates the checkbutton list for a specific webhook entry."""
        checklist_frame = webhook_data.get("checklist_frame")
        if not checklist_frame: return

        for widget in checklist_frame.winfo_children():
            widget.destroy()
        webhook_data["account_vars"] = {}

        selected_accounts_lower = {acc.lower() for acc in webhook_data.get("selected_accounts", [])}
        sorted_accounts = sorted(self.app.accounts, key=lambda x: x.get("username", "").lower())

        if not sorted_accounts:
             ttk.Label(checklist_frame, text="No accounts configured.", font=("TkDefaultFont", 8, "italic")).pack(padx=5, pady=5)
             return

        for account in sorted_accounts:
            username = account.get("username")
            if username:
                is_selected = username.lower() in selected_accounts_lower
                var = tk.BooleanVar(value=is_selected)
                cb = ttk.Checkbutton(checklist_frame, text=username, variable=var, command=lambda data=webhook_data: self._update_selected_accounts_from_checklist(data))
                cb.pack(anchor='w', fill='x', padx=5)
                webhook_data["account_vars"][username] = var

    def _toggle_account_selection(self, webhook_data, initial_state=None):
        """Shows or hides the account selection checklist based on the 'Notify All' checkbox."""
        notify_all = webhook_data["notify_all_var"].get() if initial_state is None else initial_state
        checklist_scroll_frame = webhook_data.get("checklist_scroll_frame")
        if not checklist_scroll_frame: return
        if notify_all:
             checklist_scroll_frame.pack_forget()
             webhook_data["selected_accounts"] = []
        else:
             checklist_scroll_frame.pack(fill='x', pady=(0, 5), padx=8)
             self._populate_account_checklist(webhook_data)
             self._update_selected_accounts_from_checklist(webhook_data)
        self.app.config_changed = True

    def _update_selected_accounts(self, webhook_data):
        """Updates the list of selected accounts based on listbox selection."""
        pass

    def _update_selected_accounts_from_checklist(self, webhook_data):
        """Updates the list of selected accounts based on checklist state."""
        account_vars = webhook_data.get("account_vars", {})
        selected_usernames = [username for username, var in account_vars.items() if var.get()]
        webhook_data["selected_accounts"] = selected_usernames
        self.app.config_changed = True

    def _remove_webhook_entry(self, webhook_data):
        """Removes a webhook entry UI and its data."""
        try:
            for i, entry_data in enumerate(self.webhook_entries):
                if entry_data == webhook_data:
                    self.webhook_content_frame.winfo_children()[i].destroy()
                    self.webhook_entries.pop(i); break
            for i, child in enumerate(self.webhook_content_frame.winfo_children()):
                 if isinstance(child, ttk.LabelFrame): child.configure(text=f"Webhook #{i + 1}")
            self.app.config_changed = True
        except Exception as e: getattr(self.app, 'error_logging', print)(e, "Error removing webhook entry UI")

    def get_webhook_configs_for_save(self):
         """Extracts webhook configurations from the UI elements for saving."""
         return [{"url": url, **({"account_notifications": entry.get("selected_accounts", [])} if not entry["notify_all_var"].get() else {})}
                 for entry in self.webhook_entries if (url := entry["url_entry"].get().strip())]

    def _create_stats_tab(self, parent_frame):
        """Creates the content for the Stats & Logs tab."""
        left_frame = ttk.Frame(parent_frame); left_frame.pack(side="left", fill="y", padx=(10, 5), pady=10)
        right_frame = ttk.Frame(parent_frame); right_frame.pack(side="right", fill="both", expand=True, padx=(5, 10), pady=10)

        stats_container = ttk.LabelFrame(left_frame, text="Biome Stats"); stats_container.pack(fill="x", pady=(0, 10))
        self.stats_labels = {}; biomes = list(self.app.biome_data.keys()); columns = 2; max_rows = (len(biomes) + columns - 1) // columns
        for i, biome in enumerate(biomes):
            row = i % max_rows; col = i // max_rows * 2
            try: color_hex = f"#{int(self.app.biome_data[biome].get('color', 'FFFFFF').replace('0x', ''), 16):06X}"
            except: color_hex = "#FFFFFF"
            ttk.Label(stats_container, text=f"{biome}:", anchor="e").grid(row=row, column=col, sticky="ew", padx=(5, 2), pady=2)
            label = ttk.Label(stats_container, text=str(self.app.biome_counts.get(biome, 0)), foreground=color_hex, anchor="w")
            label.grid(row=row, column=col + 1, sticky="ew", padx=(2, 5), pady=2); self.stats_labels[biome] = label
            stats_container.grid_columnconfigure(col+1, weight=1)
        self.total_biomes_label = ttk.Label(left_frame, text="Total Biomes Found: 0"); self.total_biomes_label.pack(fill="x", pady=5)
        self.session_label = ttk.Label(left_frame, text="Running Session: 00:00:00"); self.session_label.pack(fill="x", pady=5)
        self.update_stats_display()

        logs_container = ttk.LabelFrame(right_frame, text="Application Logs"); logs_container.pack(fill="both", expand=True)
        search_entry = ttk.Entry(logs_container); search_entry.pack(fill="x", padx=5, pady=(5, 0)); search_entry.insert(0, "Filter logs...")
        search_entry.bind("<FocusIn>", lambda e: e.widget.delete(0, tk.END) if e.widget.get() == "Filter logs..." else None)
        search_entry.bind("<FocusOut>", lambda e: e.widget.insert(0, "Filter logs...") if not e.widget.get() else None)
        search_entry.bind("<KeyRelease>", lambda event: self._filter_logs(event.widget.get()))
        log_text_frame = ttk.Frame(logs_container); log_text_frame.pack(expand=True, fill="both", padx=5, pady=5)
        self.logs_text = tk.Text(log_text_frame, height=15, width=40, wrap="word", state="disabled", bg=ttk.Style().lookup('TFrame', 'background'), fg="white")
        self.logs_text.pack(side="left", expand=True, fill="both")
        scrollbar = ttk.Scrollbar(log_text_frame, orient="vertical", command=self.logs_text.yview); scrollbar.pack(side="right", fill="y")
        self.logs_text.config(yscrollcommand=scrollbar.set)
        self.display_logs()

    def update_stats_display(self):
        """Updates the labels in the Stats tab with current data from the app."""
        if not self.root or not self.root.winfo_exists(): return
        total_biomes = sum(self.app.biome_counts.get(biome, 0) for biome in self.stats_labels)
        for biome, label in self.stats_labels.items():
            if label.winfo_exists(): label.config(text=str(self.app.biome_counts.get(biome, 0)))
        if self.total_biomes_label and self.total_biomes_label.winfo_exists(): self.total_biomes_label.config(text=f"Total Biomes Found: {total_biomes}")

    def update_session_timer_display(self):
        """Updates the session timer label specifically."""
        if self.session_label and self.session_label.winfo_exists(): self.session_label.config(text=f"Running Session: {self.app.get_formatted_session_time()}")

    def display_logs(self, logs_to_display=None):
        """Displays logs in the text widget, showing latest entries."""
        if not self.logs_text or not self.logs_text.winfo_exists(): return
        self.logs_text.config(state="normal"); self.logs_text.delete(1.0, "end")
        logs = logs_to_display if logs_to_display is not None else self.app.logs
        max_log_lines = 200; start_index = max(0, len(logs) - max_log_lines)
        for entry in logs[start_index:]:
            msg = f"[{entry['timestamp']}] {entry['message']}" if isinstance(entry, dict) and 'timestamp' in entry else str(entry)
            self.logs_text.insert("end", msg + "\n")
        self.logs_text.config(state="disabled"); self.logs_text.see("end")

    def append_log_display(self, log_entry):
         """Appends a single new log entry to the display efficiently."""
         if not self.logs_text or not self.logs_text.winfo_exists(): return
         msg = f"[{log_entry['timestamp']}] {log_entry['message']}" if isinstance(log_entry, dict) and 'timestamp' in log_entry else str(log_entry)
         scroll_pos = self.logs_text.yview(); at_bottom = scroll_pos[1] >= 0.95
         self.logs_text.config(state="normal"); self.logs_text.insert("end", msg + "\n"); self.logs_text.config(state="disabled")
         if at_bottom: self.logs_text.see("end")

    def _filter_logs(self, keyword):
        """Filters the displayed logs based on the keyword."""
        keyword = keyword.lower().strip()
        if keyword == "filter logs...": keyword = ""
        if not keyword: self.display_logs(); return
        filtered = [log for log in self.app.logs if keyword in (log.get("message", "").lower() if isinstance(log, dict) else str(log).lower())]
        self.display_logs(filtered)

    def _create_credit_tab(self, parent_frame):
        """Creates the content for the Credits tab."""
        frame = ttk.Frame(parent_frame, padding=20); frame.pack(expand=True, fill="both")
        ttk.Label(frame, text="MultiScope", font=("Arial", 16, "bold")).pack(pady=(10, 5))
        ttk.Label(frame, text=f"Version {self.app.version}").pack(pady=5)
        ttk.Label(frame, text="A Sols RNG Biome & Multi-Account Tracker.", wraplength=400).pack(pady=10)

        credits_frame = ttk.LabelFrame(frame, text="Credits", padding=10); credits_frame.pack(fill="x", pady=10)
        ttk.Label(credits_frame, text="Created by: cresqnt (Patch fix by Manas, join discord.gg/oppression)", font=("Arial", 10, "bold")).pack(anchor="w", padx=10, pady=5)
        ttk.Label(credits_frame, text="Contributors & Inspirations:", font=("Arial", 10, "bold")).pack(anchor="w", padx=10, pady=(10, 0))
        contributors = ["Maxstellar (Original Inspiration)", "Bored Man (Biome Detection Rewrite)", "stxrrygold/@lolst_gold (Helping with new Merchant detection)"]
        for c in contributors: ttk.Label(credits_frame, text=f"• {c}").pack(anchor="w", padx=30, pady=2)

        support_frame = ttk.LabelFrame(frame, text="Support & Links", padding=10); support_frame.pack(fill="x", pady=10)
        dc_label = ttk.Label(support_frame, text="Discord Server: Join Here", cursor="hand2", foreground="#007bff")
        dc_label.pack(anchor="w", padx=10, pady=5); dc_label.bind("<Button-1>", lambda e: webbrowser.open("https://discord.gg/6cuCu6ymkX")); create_tooltip(dc_label, "Join Discord")
        gh_label = ttk.Label(support_frame, text="GitHub Repository: View Source", cursor="hand2", foreground="#007bff")
        gh_label.pack(anchor="w", padx=10, pady=5); gh_label.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/cresqnt-sys/MultiScope")); create_tooltip(gh_label, "View Source")
        scope_dev_label = ttk.Label(support_frame, text="Scope Development Website: scopedevelopment.tech", cursor="hand2", foreground="#007bff")
        scope_dev_label.pack(anchor="w", padx=10, pady=5); scope_dev_label.bind("<Button-1>", lambda e: webbrowser.open("https://scopedevelopment.tech")); create_tooltip(scope_dev_label, "Visit Scope Development")
        ttk.Label(frame, text="© 2024 cresqnt. All rights reserved.").pack(side="bottom", pady=(10, 5), anchor='s')

    def show_message_box(self, title, message, msg_type="info"):
        """Shows a standard message box."""
        if self.root:
            func = messagebox.showerror if msg_type == "error" else (messagebox.showwarning if msg_type == "warning" else messagebox.showinfo)
            self.root.after(0, lambda: func(title, message, parent=self.root))
        else: print(f"[{title}] {message}")

    def ask_yes_no(self, title, question):
         """Shows a yes/no question box and returns boolean result."""
         if self.root: return messagebox.askyesno(title, question, parent=self.root)
         else: print(f"[Question] {title}: {question} (Auto-answering No)"); return False

    def open_biome_notification_settings(self):
        """Opens the window to configure biome notification settings."""
        win = ttk.Toplevel(self.root); win.title("Biome Notification Settings"); win.geometry("400x450"); win.transient(self.root); win.grab_set(); win.resizable(False, False)
        mf = ttk.Frame(win, padding=10); mf.pack(fill='both', expand=True)
        ttk.Label(mf, text="Configure Biome Notifications", font=("TkDefaultFont", 12, "bold")).pack(pady=(0, 10))
        ttk.Label(mf, text="Enable/disable webhook notifications per biome:", wraplength=350).pack(pady=(0, 10))
        sf = ttk.Frame(mf); sf.pack(fill="both", expand=True, pady=5)
        cvs = tk.Canvas(sf, highlightthickness=0, bg=ttk.Style().lookup('TFrame', 'background')); sb = ttk.Scrollbar(sf, orient="vertical", command=cvs.yview)
        cba = ttk.Frame(cvs); cvs.pack(side="left", fill="both", expand=True); sb.pack(side="right", fill="y"); cvs.configure(yscrollcommand=sb.set)
        fid = cvs.create_window((0, 0), window=cba, anchor="nw")
        def usc(e): cvs.configure(scrollregion=cvs.bbox("all"))
        cba.bind("<Configure>", usc); cvs.bind("<Configure>", lambda e: cvs.itemconfig(fid, width=e.width))
        cvs.bind_all("<MouseWheel>", lambda e: cvs.yview_scroll(-1*(e.delta//120), "units")); win.bind("<Destroy>", lambda e: cvs.unbind_all("<MouseWheel>"))

        bv = {}; cfg = self.app.config.get("biome_notification_enabled", {})
        for b in sorted(self.app.biome_data.keys()):
             f = ttk.Frame(cba); f.pack(fill='x', pady=2, padx=5)
             aen = b in ["GLITCHED", "DREAMSPACE", "BLAZING SUN"]
             always_off = b == "NORMAL"
             iv = True if aen else (False if always_off else cfg.get(b, True))
             var = tk.BooleanVar(value=iv)
             cb = ttk.Checkbutton(f, text=b, variable=var, state="disabled" if aen or always_off else "normal")
             cb.pack(side='left')
             bv[b] = var
             if aen: ttk.Label(f, text="(Always Notify)", foreground="green").pack(side='right', padx=5)
             elif always_off: ttk.Label(f, text="(Never Notify)", foreground="red").pack(side='right', padx=5)
        bf = ttk.Frame(win, padding=(0, 10)); bf.pack(fill='x')
        def svs():
            ns = {b: v.get() for b, v in bv.items()}
            ns["GLITCHED"] = ns["DREAMSPACE"] = ns["BLAZING SUN"] = True
            ns["NORMAL"] = False
            self.app.config["biome_notification_enabled"] = ns
            self.app.config_changed = True
            win.destroy()
            self.show_message_box("Success", "Settings saved!", "info")
        def sa(): [v.set(True) for b, v in bv.items() if b not in ["GLITCHED", "DREAMSPACE", "BLAZING SUN", "NORMAL"]]
        def sn(): [v.set(False) for b, v in bv.items() if b not in ["GLITCHED", "DREAMSPACE", "BLAZING SUN"]]
        ttk.Button(bf, text="Save", command=svs, style="success.TButton", width=10).pack(side='right', padx=5)
        ttk.Button(bf, text="Cancel", command=win.destroy, style="danger.TButton", width=10).pack(side='right', padx=5)
        ttk.Button(bf, text="Select All", command=sa, style="info.TButton", width=10).pack(side='left', padx=5)
        ttk.Button(bf, text="Select None", command=sn, style="secondary.TButton", width=10).pack(side='left', padx=5)
        win.wait_window()

    def open_accounts_manager(self):
        """Opens the Toplevel window to manage accounts."""
        if hasattr(self, 'accounts_window') and self.accounts_window.winfo_exists():
            self.accounts_window.lift()
            return

        self.accounts_window = tk.Toplevel(self.root)
        self.accounts_window.title("Accounts Manager")
        self.accounts_window.geometry("650x450") 
        self.accounts_window.transient(self.root)
        self.accounts_window.grab_set()
        self.accounts_window.columnconfigure(0, weight=1) 
        self.accounts_window.rowconfigure(2, weight=1) 

        title_label = ttk.Label(self.accounts_window, text="Manage Accounts", font=("Arial", 14, "bold"))
        title_label.grid(row=0, column=0, pady=(10, 5), padx=10, sticky="w")
        subtitle_label = ttk.Label(self.accounts_window, text="Add/edit accounts for multi-instance tracking. Only active accounts are monitored.")
        subtitle_label.grid(row=1, column=0, pady=(0, 15), padx=10, sticky="w")

        header_frame = ttk.Frame(self.accounts_window)
        header_frame.grid(row=2, column=0, sticky="ew", padx=10)
        header_frame.columnconfigure(0, weight=2) 
        header_frame.columnconfigure(1, weight=3) 
        header_frame.columnconfigure(2, weight=0, minsize=60) 
        header_frame.columnconfigure(3, weight=0, minsize=70) 

        ttk.Label(header_frame, text="Username").grid(row=0, column=0, padx=5, sticky="w")
        ttk.Label(header_frame, text="Private Server Link (Optional)").grid(row=0, column=1, padx=5, sticky="w")
        ttk.Label(header_frame, text="Active").grid(row=0, column=2, padx=(15, 5), sticky="w") 
        ttk.Label(header_frame, text="Actions").grid(row=0, column=3, padx=5, sticky="w")
        ttk.Separator(header_frame, orient="horizontal").grid(row=1, column=0, columnspan=4, sticky="ew", pady=(2, 5))

        scroll_container = ttk.Frame(self.accounts_window)
        scroll_container.grid(row=3, column=0, sticky="nsew", padx=10, pady=5)
        scroll_container.rowconfigure(0, weight=1)
        scroll_container.columnconfigure(0, weight=1)

        accounts_canvas = tk.Canvas(scroll_container, highlightthickness=0, bg=ttk.Style().lookup('TFrame', 'background'))
        accounts_scrollbar = ttk.Scrollbar(scroll_container, orient="vertical", command=accounts_canvas.yview)
        accounts_canvas.configure(yscrollcommand=accounts_scrollbar.set)

        accounts_canvas.grid(row=0, column=0, sticky="nsew")
        accounts_scrollbar.grid(row=0, column=1, sticky="ns")

        accounts_frame = ttk.Frame(accounts_canvas)
        canvas_frame_id = accounts_canvas.create_window((0, 0), window=accounts_frame, anchor="nw")

        accounts_frame.columnconfigure(0, weight=2)
        accounts_frame.columnconfigure(1, weight=3)
        accounts_frame.columnconfigure(2, weight=0, minsize=60) 
        accounts_frame.columnconfigure(3, weight=0, minsize=70) 

        def configure_scroll_region(event):
            accounts_canvas.configure(scrollregion=accounts_canvas.bbox("all"))
        def configure_frame_width(event):
            canvas_width = event.width
            accounts_canvas.itemconfig(canvas_frame_id, width=canvas_width)

            accounts_frame.config(width=canvas_width)

        accounts_canvas.bind('<Configure>', configure_frame_width)
        accounts_frame.bind('<Configure>', configure_scroll_region)

        def _on_account_mousewheel(event):
            if event.delta: delta = -1 * (event.delta // 120)
            elif event.num == 5: delta = 1 
            elif event.num == 4: delta = -1 
            else: delta = 0
            accounts_canvas.yview_scroll(delta, "units")

        accounts_canvas.bind_all("<MouseWheel>", _on_account_mousewheel) 

        self.accounts_window.bind("<Destroy>", lambda e: accounts_canvas.unbind_all("<MouseWheel>"))

        account_widgets = [] 

        def add_account_row(account=None):
            """Adds a row for an account entry using grid."""
            row_index = len(account_widgets) 

            username_var = tk.StringVar(value=account.get("username", "") if account else "")
            ps_link_var = tk.StringVar(value=account.get("ps_link", "") if account else "")
            active_var = tk.BooleanVar(value=account.get("active", True) if account else True)

            username_entry = ttk.Entry(accounts_frame, textvariable=username_var)
            username_entry.grid(row=row_index, column=0, padx=5, pady=3, sticky="ew")
            ps_link_entry = ttk.Entry(accounts_frame, textvariable=ps_link_var)
            ps_link_entry.grid(row=row_index, column=1, padx=5, pady=3, sticky="ew")

            active_check_frame = ttk.Frame(accounts_frame)
            active_check_frame.grid(row=row_index, column=2, padx=5, pady=3, sticky="w")
            active_check = ttk.Checkbutton(active_check_frame, variable=active_var)
            active_check.pack(anchor="w") 

            entry_data = {
                "username_var": username_var,
                "ps_link_var": ps_link_var,
                "active_var": active_var,

                "widgets": [username_entry, ps_link_entry, active_check_frame, active_check]
            }

            def remove_row():

                for widget in entry_data["widgets"]:
                    if widget and widget.winfo_exists():
                        widget.destroy()

                if entry_data in account_widgets:
                    account_widgets.remove(entry_data)
                else:

                    for i, data in enumerate(account_widgets):
                        if data["username_var"] == entry_data["username_var"]: 
                           account_widgets.pop(i)
                           break

                for idx, data in enumerate(account_widgets):
                    current_widgets = data["widgets"]

                    current_widgets[0].grid(row=idx, column=0, padx=5, pady=3, sticky="ew")

                    current_widgets[1].grid(row=idx, column=1, padx=5, pady=3, sticky="ew")

                    current_widgets[2].grid(row=idx, column=2, padx=5, pady=3, sticky="w")

                    current_widgets[4].grid(row=idx, column=3, padx=5, pady=3, sticky="w")

                if not account_widgets:
                     pass

                accounts_canvas.configure(scrollregion=accounts_canvas.bbox("all"))

            remove_button_frame = ttk.Frame(accounts_frame)
            remove_button_frame.grid(row=row_index, column=3, padx=5, pady=3, sticky="w")
            remove_button = ttk.Button(remove_button_frame, text="Remove", command=remove_row, style="danger.TButton", width=8)
            remove_button.pack(anchor="w") 

            entry_data["widgets"].extend([remove_button_frame, remove_button])
            entry_data["remove_func"] = remove_row

            account_widgets.append(entry_data)

            accounts_canvas.configure(scrollregion=accounts_canvas.bbox("all"))

        def save_accounts():
            """Saves the current state of the accounts list."""
            updated_accounts = []
            for entry_data in account_widgets:
                username = entry_data["username_var"].get().strip()
                ps_link = entry_data["ps_link_var"].get().strip()
                is_active = entry_data["active_var"].get()
                if username: 
                    updated_accounts.append({
                        "username": username,
                        "ps_link": ps_link,
                        "active": is_active
                    })

            self.app.accounts = updated_accounts
            self.app.config["accounts"] = updated_accounts
            self.app.config_changed = True
            self.app._initialize_state() 
            self.refresh_webhook_account_lists() 
            self.accounts_window.destroy()
            self.show_message_box("Accounts Saved", f"{len(updated_accounts)} account(s) saved successfully.")

        if self.app.accounts:
            for acc in self.app.accounts:
                add_account_row(acc)
        else:
            add_account_row() 

        button_frame = ttk.Frame(self.accounts_window)

        button_frame.grid(row=4, column=0, sticky="ew", pady=(15, 10), padx=10)
        button_frame.columnconfigure(0, weight=1) 

        add_btn = ttk.Button(button_frame, text="Add Account", command=add_account_row, style="info.TButton")
        add_btn.grid(row=0, column=1, padx=5) 
        save_btn = ttk.Button(button_frame, text="Save Changes", command=save_accounts, style="success.TButton")
        save_btn.grid(row=0, column=2, padx=5) 
        cancel_btn = ttk.Button(button_frame, text="Cancel", command=self.accounts_window.destroy, style="secondary.TButton")
        cancel_btn.grid(row=0, column=3, padx=5) 

        self.accounts_window.protocol("WM_DELETE_WINDOW", lambda: self.accounts_window.destroy()) 

        self.accounts_window.update_idletasks() 
        accounts_canvas.configure(scrollregion=accounts_canvas.bbox("all"))

    def refresh_webhook_account_lists(self):
        """Refreshes the account checklists in all webhook entries."""
        for webhook_data in self.webhook_entries: self._populate_account_checklist(webhook_data)

    def _create_merchant_tab(self, parent_frame):
        """Creates the content for the Merchants tab."""
        master_frame = ttk.Frame(parent_frame, padding=10)
        master_frame.pack(fill="both", expand=True)

        ttk.Label(master_frame, text="Merchant Notification Settings", font=("Arial", 12, "bold")).pack(pady=(0,10))

        # Enable/Disable Checkbox
        enable_frame = ttk.Frame(master_frame)
        enable_frame.pack(fill='x', pady=5)
        self.merchant_notify_var = tk.BooleanVar(value=self.app.detection_manager.merchant_notification_enabled)
        ttk.Checkbutton(enable_frame, text="Enable Merchant Notifications (Master Switch)", variable=self.merchant_notify_var, command=self._save_merchant_settings).pack(anchor='w')

        # Individual Merchant Toggles
        self.merchant_jester_notify_var = tk.BooleanVar(value=self.app.detection_manager.merchant_jester_enabled)
        ttk.Checkbutton(enable_frame, text="Enable Jester Notifications", variable=self.merchant_jester_notify_var, command=self._save_merchant_settings).pack(anchor='w', padx=(20,0))
        
        self.merchant_mari_notify_var = tk.BooleanVar(value=self.app.detection_manager.merchant_mari_enabled)
        ttk.Checkbutton(enable_frame, text="Enable Mari Notifications", variable=self.merchant_mari_notify_var, command=self._save_merchant_settings).pack(anchor='w', padx=(20,0))

        # Webhook URL Entry
        webhook_url_frame = ttk.LabelFrame(master_frame, text="Merchant Webhook URL")
        webhook_url_frame.pack(fill='x', pady=10)
        
        url_inner_frame = ttk.Frame(webhook_url_frame, padding=5)
        url_inner_frame.pack(fill='x')

        self.merchant_webhook_url_entry = ttk.Entry(url_inner_frame, show="*")
        self.merchant_webhook_url_entry.insert(0, self.app.detection_manager.merchant_webhook_url)
        self.merchant_webhook_url_entry.pack(side='left', fill='x', expand=True, padx=(0,10))
        
        show_btn = ttk.Button(url_inner_frame, text="Show", command=lambda: self.merchant_webhook_url_entry.configure(show=""), style="secondary.TButton", width=6)
        show_btn.pack(side='left', padx=(0,5))
        hide_btn = ttk.Button(url_inner_frame, text="Hide", command=lambda: self.merchant_webhook_url_entry.configure(show="*"), style="secondary.TButton", width=6)
        hide_btn.pack(side='left')
        
        # --- Jester Ping Settings ---
        jester_ping_frame = ttk.LabelFrame(master_frame, text="Jester Ping Settings")
        jester_ping_frame.pack(fill='x', pady=10, after=webhook_url_frame)
        jester_ping_inner_frame = ttk.Frame(jester_ping_frame, padding=5)
        jester_ping_inner_frame.pack(fill='x')

        ttk.Label(jester_ping_inner_frame, text="ID / Tag:").pack(side='left', padx=(0,5))
        self.jester_ping_id_entry = ttk.Entry(jester_ping_inner_frame)
        self.jester_ping_id_entry.insert(0, self.app.detection_manager.merchant_jester_ping_config.get("id", ""))
        self.jester_ping_id_entry.pack(side='left', fill='x', expand=True, padx=(0,10))
        create_tooltip(self.jester_ping_id_entry, "Enter User ID, Role ID, @everyone, @here, or a full ping tag like <@USER_ID>.")

        ttk.Label(jester_ping_inner_frame, text="Type:").pack(side='left', padx=(0,5))
        self.jester_ping_type_var = tk.StringVar(value=self.app.detection_manager.merchant_jester_ping_config.get("type", "None"))
        self.jester_ping_type_combo = ttk.Combobox(jester_ping_inner_frame, textvariable=self.jester_ping_type_var, 
                                                 values=["None", "User ID", "Role ID"], state="readonly", width=10)
        self.jester_ping_type_combo.pack(side='left')
        create_tooltip(self.jester_ping_type_combo, "Select 'User ID' or 'Role ID' if providing a raw ID above. Select 'None' if the ID field contains a full tag (e.g. <@&ID>) or specific keyword (e.g. @everyone).")

        # --- Mari Ping Settings ---
        mari_ping_frame = ttk.LabelFrame(master_frame, text="Mari Ping Settings")
        mari_ping_frame.pack(fill='x', pady=10, after=jester_ping_frame)
        mari_ping_inner_frame = ttk.Frame(mari_ping_frame, padding=5)
        mari_ping_inner_frame.pack(fill='x')

        ttk.Label(mari_ping_inner_frame, text="ID / Tag:").pack(side='left', padx=(0,5))
        self.mari_ping_id_entry = ttk.Entry(mari_ping_inner_frame)
        self.mari_ping_id_entry.insert(0, self.app.detection_manager.merchant_mari_ping_config.get("id", ""))
        self.mari_ping_id_entry.pack(side='left', fill='x', expand=True, padx=(0,10))
        create_tooltip(self.mari_ping_id_entry, "Enter User ID, Role ID, @everyone, @here, or a full ping tag like <@USER_ID>.")

        ttk.Label(mari_ping_inner_frame, text="Type:").pack(side='left', padx=(0,5))
        self.mari_ping_type_var = tk.StringVar(value=self.app.detection_manager.merchant_mari_ping_config.get("type", "None"))
        self.mari_ping_type_combo = ttk.Combobox(mari_ping_inner_frame, textvariable=self.mari_ping_type_var, 
                                               values=["None", "User ID", "Role ID"], state="readonly", width=10)
        self.mari_ping_type_combo.pack(side='left')
        create_tooltip(self.mari_ping_type_combo, "Select 'User ID' or 'Role ID' if providing a raw ID above. Select 'None' if the ID field contains a full tag (e.g. <@&ID>) or specific keyword (e.g. @everyone).")

        # Buttons Frame
        buttons_frame = ttk.Frame(master_frame)
        buttons_frame.pack(fill='x', pady=20, side='bottom')

        save_btn = ttk.Button(buttons_frame, text="Save Merchant Settings", command=self._save_merchant_settings, style="success.TButton")
        save_btn.pack(side='left', padx=5)
        
        test_btn = ttk.Button(buttons_frame, text="Test Merchant Webhook", command=self._test_merchant_webhook, style="info.TButton")
        test_btn.pack(side='left', padx=5)
        create_tooltip(test_btn, "Sends a test Jester notification to the configured merchant webhook URL.")

    def _save_merchant_settings(self):
        """Saves the merchant notification settings from the GUI to the app config and DetectionManager."""
        try:
            new_url = self.merchant_webhook_url_entry.get().strip()
            new_master_enabled_status = self.merchant_notify_var.get()
            new_jester_enabled_status = self.merchant_jester_notify_var.get()
            new_mari_enabled_status = self.merchant_mari_notify_var.get()

            new_jester_ping_id = self.jester_ping_id_entry.get().strip()
            new_jester_ping_type = self.jester_ping_type_var.get()
            new_mari_ping_id = self.mari_ping_id_entry.get().strip()
            new_mari_ping_type = self.mari_ping_type_var.get()

            jester_ping_config = {"id": new_jester_ping_id, "type": new_jester_ping_type}
            mari_ping_config = {"id": new_mari_ping_id, "type": new_mari_ping_type}

            # Update DetectionManager directly
            self.app.detection_manager.merchant_webhook_url = new_url
            self.app.detection_manager.merchant_notification_enabled = new_master_enabled_status
            self.app.detection_manager.merchant_jester_enabled = new_jester_enabled_status
            self.app.detection_manager.merchant_mari_enabled = new_mari_enabled_status
            self.app.detection_manager.merchant_jester_ping_config = jester_ping_config
            self.app.detection_manager.merchant_mari_ping_config = mari_ping_config
            
            # Update app level attributes which get saved to config by app.save_state()
            self.app.merchant_webhook_url = new_url
            self.app.merchant_notification_enabled = new_master_enabled_status
            self.app.merchant_jester_enabled = new_jester_enabled_status
            self.app.merchant_mari_enabled = new_mari_enabled_status
            self.app.merchant_jester_ping_config = jester_ping_config
            self.app.merchant_mari_ping_config = mari_ping_config

            self.app.config_changed = True # Mark for saving
            self.app.save_state(periodic=True) # Trigger a save
            self.show_message_box("Success", "Merchant settings saved!", "info")
            self.app.append_log("Merchant settings updated and saved.")

        except Exception as e:
            error_logging(e, "Error saving merchant settings")
            self.show_message_box("Error", f"Failed to save merchant settings: {e}", "error")

    def _test_merchant_webhook(self):
        """Sends a test merchant (Jester) notification to the configured merchant webhook URL."""
        webhook_url = self.merchant_webhook_url_entry.get().strip()
        if not webhook_url:
            self.show_message_box("Error", "Merchant webhook URL is empty.", "error")
            return

        self.app.append_log(f"Attempting to send test merchant webhook to ...{webhook_url[-10:]}")

        # Use the send_merchant_webhook method from detection_manager for consistency
        # Need to provide some mock data for the test
        test_username = "TestUser" # Default username
        if self.app.accounts: # Check if there are any configured accounts
            first_account = self.app.accounts[0]
            if first_account and first_account.get("username"):
                test_username = first_account.get("username")
                self.app.append_log(f"Test merchant webhook will use account: {test_username}")
            else:
                self.app.append_log(f"First account has no username, using default '{test_username}' for test.")
        else:
            self.app.append_log(f"No accounts configured, using default '{test_username}' for test.")
            
        test_merchant_name = "Jester"
        test_event_time_utc = datetime.now(timezone.utc) # Correct way to get timezone-aware UTC now

        # Temporarily set the manager's URL and Jester ping config for the test, then restore
        original_dm_url = self.app.detection_manager.merchant_webhook_url
        original_jester_ping_config = self.app.detection_manager.merchant_jester_ping_config.copy() # Important to copy

        current_jester_ping_id = self.jester_ping_id_entry.get().strip()
        current_jester_ping_type = self.jester_ping_type_var.get()
        
        self.app.detection_manager.merchant_webhook_url = webhook_url
        self.app.detection_manager.merchant_jester_ping_config = {
            "id": current_jester_ping_id,
            "type": current_jester_ping_type
        }
        
        try:
            # Call the actual send method
            self.app.detection_manager.send_merchant_webhook(test_username, test_merchant_name, test_event_time_utc)
            # send_merchant_webhook itself logs success/failure and handles rate limit display
            # It doesn't return a status directly for this test function to show a message box easily,
            # so we rely on its internal logging and assume success if no exception.
            # A more robust test might involve a direct requests.post like the biome test webhook.
            # For now, let's assume the internal logging of send_merchant_webhook is sufficient.
            # We can add a simple success message if no exception.
            self.show_message_box("Test Sent", "Test merchant webhook initiated. Check Discord and application logs for status.", "info")

        except Exception as e:
            error_logging(e, f"Error during test_merchant_webhook call to ...{webhook_url[-10:]}")
            self.show_message_box("Error", f"Failed to send test merchant webhook: {e}", "error")
        finally:
            # Restore the original URL and Jester ping config in detection_manager
            self.app.detection_manager.merchant_webhook_url = original_dm_url
            self.app.detection_manager.merchant_jester_ping_config = original_jester_ping_config

class SnippingWidget:
    def __init__(self, root, config_key=None, callback=None):
        self.root = root; self.config_key = config_key; self.callback = callback
        self.snipping_window = None; self.begin_x = None; self.begin_y = None
        self.end_x = None; self.end_y = None; self.canvas = None

    def start(self):
        self.snipping_window = ttk.Toplevel(self.root)
        self.snipping_window.attributes('-fullscreen', True); self.snipping_window.attributes('-alpha', 0.3)
        self.snipping_window.configure(cursor="crosshair"); self.snipping_window.bind("<Escape>", lambda e: self.snipping_window.destroy())
        self.canvas = tk.Canvas(self.snipping_window, cursor="crosshair", bg="grey", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_press); self.canvas.bind("<B1-Motion>", self.on_mouse_drag); self.canvas.bind("<ButtonRelease-1>", self.on_mouse_release)

    def on_mouse_press(self, event): self.begin_x = event.x; self.begin_y = event.y; self.canvas.delete("selection_rect")
    def on_mouse_drag(self, event): self.end_x, self.end_y = event.x, event.y; self.canvas.delete("selection_rect"); self.canvas.create_rectangle(self.begin_x, self.begin_y, self.end_x, self.end_y, outline="white", width=2, tag="selection_rect")
    def on_mouse_release(self, event):
        self.end_x = event.x; self.end_y = event.y; x1 = min(self.begin_x, self.end_x); y1 = min(self.begin_y, self.end_y)
        x2 = max(self.begin_x, self.end_x); y2 = max(self.begin_y, self.end_y); width = x2 - x1; height = y2 - y1
        if width > 0 and height > 0: self.capture_region(x1, y1, width, height)
        else: print("Snipping cancelled or region too small.")
        if self.snipping_window: self.snipping_window.destroy(); self.snipping_window = None

    def capture_region(self, x, y, width, height):
        region = [x, y, width, height]; print(f"Region captured: {region}")
        if self.callback: self.callback(self.config_key, region)

try:
    from app import MultiScopeApp 

    if __name__ == "__main__":
        print(f"Starting {APP_NAME} v{APP_VERSION}...")
        try:

            app = MultiScopeApp(gui_manager_class=GuiManager)
            app.run() 
        except Exception as e:
            print("\n--- UNHANDLED EXCEPTION ---")
            error_logging(e, "Unhandled exception during application execution")
            print("---------------------------")
            input("An unexpected error occurred. Press Enter to exit.")

except ImportError as e:
    print(f"\n--- IMPORT ERROR ---")
    print(f"Failed to import necessary modules: {e}")
    traceback.print_exc()
    print("---------------------")
    print("Please ensure all required files (main.py, app.py, detection.py, utils.py, antiafk.py [optional]) are present.")
    input("Import error occurred. Press Enter to exit.")

except Exception as e:
    print("\n--- FATAL INITIALIZATION ERROR ---")
    print(f"An error occurred before the application could fully start: {e}")
    traceback.print_exc()
    print("----------------------------------")
    input("Fatal error during initialization. Press Enter to exit.")
