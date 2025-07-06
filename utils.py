import json
import os
import sys
import time
import traceback
import shutil
import requests
import webbrowser
import locale
import winreg
from datetime import datetime, timedelta
from tkinter import filedialog, messagebox
import ttkbootstrap as ttk
import tkinter as tk 

APP_NAME = "MultiScope"
CONFIG_DIR = os.path.join(os.getenv('APPDATA'), APP_NAME)
ERROR_LOG_FILENAME = "error_logs.txt"
LOGS_FILENAME = "biome_logs.json"
CONFIG_FILENAME = "config.json"
BIOMES_DATA_FILENAME = "biomes_data.json"
AURAS_FILENAME = "auras.json"
MAX_ERROR_LOG_SIZE = 3 * 1024 * 1024 

_error_log_path = os.path.join(CONFIG_DIR, ERROR_LOG_FILENAME)

def error_logging(exception, custom_message=None, max_log_size=MAX_ERROR_LOG_SIZE):
    """Log errors to a file in the AppData directory."""
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        error_message = f"[{timestamp}] {custom_message if custom_message else 'ERROR'}: {str(exception)}\n"
        error_message += f"Traceback:\n{traceback.format_exc()}\n"

        print(error_message) 

        try:
            if os.path.exists(_error_log_path) and os.path.getsize(_error_log_path) > max_log_size:
                backup_path = os.path.join(CONFIG_DIR, f"error_logs_backup_{int(time.time())}.txt")
                shutil.copy2(_error_log_path, backup_path)

                with open(_error_log_path, "w", encoding='utf-8') as f:
                    f.write(f"[{timestamp}] Log file rotated due to size limit\n")
                    f.write(error_message)
            else:
                with open(_error_log_path, "a", encoding='utf-8') as f:
                    f.write(error_message)
        except Exception as log_error:
            print(f"CRITICAL: Failed to write to error log: {str(log_error)}")

    except Exception as e:

        print(f"CRITICAL: Error in error_logging function itself: {str(e)}")
        print(f"Original error: {custom_message} - {str(exception)}")
        traceback.print_exc()

def load_json_data(filename, default_data=None, legacy_paths=None):
    """Loads JSON data from AppData, handles migration from legacy paths, and returns default if needed."""
    appdata_path = os.path.join(CONFIG_DIR, filename)
    os.makedirs(CONFIG_DIR, exist_ok=True)

    if os.path.exists(appdata_path):
        try:
            with open(appdata_path, "r", encoding='utf-8') as file:
                return json.load(file)
        except json.JSONDecodeError as e:
            error_logging(e, f"Error decoding JSON from {appdata_path}. Trying to recover/reset.")

            try:

                backup_path = appdata_path + ".corrupt_backup"
                if os.path.exists(backup_path): os.remove(backup_path) 
                os.rename(appdata_path, backup_path)
                print(f"WARNING: Corrupted {filename} backed up to {backup_path}. Using default data.")
                if default_data is not None:
                    save_json_data(filename, default_data) 
                    return default_data
                else:
                    return {} 
            except Exception as backup_e:
                 error_logging(backup_e, f"Failed to backup corrupted {filename}.")
                 return default_data if default_data is not None else {}
        except Exception as e:
            error_logging(e, f"Failed to load {filename} from AppData. Using default.")
            return default_data if default_data is not None else {}

    if legacy_paths:
        for path in legacy_paths:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding='utf-8') as file:
                        data = json.load(file)

                    save_json_data(filename, data)
                    print(f"Migrated {filename} from {path} to {appdata_path}")

                    return data
                except Exception as e:
                    error_logging(e, f"Failed to load or migrate legacy {filename} from {path}. Skipping.")
                    continue 

    if default_data is not None:
        print(f"{filename} not found. Creating default file in AppData.")
        save_json_data(filename, default_data)
        return default_data
    else:
         print(f"WARNING: {filename} not found and no default data provided.")
         return {} 

def save_json_data(filename, data):
    """Saves data to a JSON file in the AppData directory."""
    appdata_path = os.path.join(CONFIG_DIR, filename)
    os.makedirs(CONFIG_DIR, exist_ok=True)
    try:

        if os.path.exists(appdata_path):
             try: os.chmod(appdata_path, 0o666)
             except Exception as chmod_e: error_logging(chmod_e, f"Could not set permissions for {appdata_path}")

        with open(appdata_path, "w", encoding='utf-8') as file:
            json.dump(data, file, indent=4)

    except Exception as e:
        error_logging(e, f"Error saving data to {filename}")

def load_config(default_biome_data_keys):
    """Loads the main configuration file."""
    default_config = {
        "biome_counts": {biome: 0 for biome in default_biome_data_keys},
        "session_time": "0:00:00",
        "accounts": [],
        "webhooks": [],
        "merchant_webhook_url": "",
        "merchant_notification_enabled": True,
        "merchant_jester_enabled": True,
        "merchant_mari_enabled": True,
        "merchant_jester_ping_config": {"id": "", "type": "None"},
        "merchant_mari_ping_config": {"id": "", "type": "None"}
    }
    legacy_paths = [
        "config.json",
        "source_code/config.json",
        os.path.join(os.path.dirname(sys.argv[0]), "config.json"),
        os.path.join(os.path.dirname(sys.argv[0]), "source_code/config.json")
    ]

    config = load_json_data(CONFIG_FILENAME, default_config, legacy_paths)

    # Check if we need to add any new biomes to the config
    config_updated = False

    # Ensure biome_counts has all biomes
    if "biome_counts" not in config:
        config["biome_counts"] = {}
    for biome in default_biome_data_keys:
        if biome not in config["biome_counts"]:
            print(f"Adding new biome '{biome}' to config biome_counts.")
            config["biome_counts"][biome] = 0
            config_updated = True

    # Ensure biome_notification_enabled has all biomes (default to True, except special cases)
    if "biome_notification_enabled" not in config:
        config["biome_notification_enabled"] = {}
    for biome in default_biome_data_keys:
        if biome not in config["biome_notification_enabled"]:
            # Default notification settings: always on for special biomes, off for NORMAL, on for others
            if biome in ["GLITCHED", "DREAMSPACE", "BLAZING SUN"]:
                default_enabled = True
            elif biome == "NORMAL":
                default_enabled = False
            else:
                default_enabled = True
            print(f"Adding new biome '{biome}' to config biome_notification_enabled (default: {default_enabled}).")
            config["biome_notification_enabled"][biome] = default_enabled
            config_updated = True

    # Ensure biome_notifier has all biomes (default to "Message", except special cases)
    if "biome_notifier" not in config:
        config["biome_notifier"] = {}
    for biome in default_biome_data_keys:
        if biome not in config["biome_notifier"]:
            # Default notifier settings: Ping for special biomes, Message for others
            if biome in ["GLITCHED", "DREAMSPACE", "BLAZING SUN"]:
                default_notifier = "Ping"
            else:
                default_notifier = "Message"
            print(f"Adding new biome '{biome}' to config biome_notifier (default: {default_notifier}).")
            config["biome_notifier"][biome] = default_notifier
            config_updated = True

    # Save the updated config if new biomes were added
    if config_updated:
        print("Saving updated config with new biomes.")
        save_json_data(CONFIG_FILENAME, config)

    return config

def save_config(config_data):
    """Saves the main configuration file."""
    save_json_data(CONFIG_FILENAME, config_data)

def load_biome_data():
    """Loads biome data. (thanks maxstellar for the images)"""
    default_data = {
        "WINDY": {"emoji": "🌀", "color": "0xFFFFFF", "thumbnail_url": "https://maxstellar.tech/biome_thumb/WINDY.png"},
        "RAINY": {"emoji": "🌧️", "color": "0x55925F", "thumbnail_url": "https://maxstellar.tech/biome_thumb/RAINY.png"},
        "SNOWY": {"emoji": "❄️", "color": "0xFFFFFF", "thumbnail_url": "https://maxstellar.tech/biome_thumb/SNOWY.png"},
        "SAND STORM": {"emoji": "🏜️", "color": "0xFFA500", "thumbnail_url": "https://maxstellar.tech/biome_thumb/SAND%20STORM.png"},
        "HELL": {"emoji": "🔥", "color": "0xFB4F29", "thumbnail_url": "https://maxstellar.tech/biome_thumb/HELL.png"},
        "STARFALL": {"emoji": "🌠", "color": "0xFFFFFF", "thumbnail_url": "https://maxstellar.tech/biome_thumb/STARFALL.png"},
        "CORRUPTION": {"emoji": "🌑", "color": "0x800080", "thumbnail_url": "https://maxstellar.tech/biome_thumb/CORRUPTION.png"},
        "NULL": {"emoji": "🌫️", "color": "0x808080", "thumbnail_url": "https://maxstellar.tech/biome_thumb/NULL.png"},
        "GLITCHED": {"emoji": "⚠️", "color": "0xFFFF00", "thumbnail_url": "https://i.postimg.cc/mDzwFfX1/GLITCHED.png"},
        "DREAMSPACE": {"emoji": "💤", "color": "0xFF00FF", "thumbnail_url": "https://maxstellar.tech/biome_thumb/DREAMSPACE.png"},
        "BLAZING SUN": {"emoji": "☀️", "color": "0xFFD700", "thumbnail_url": "https://static.wikia.nocookie.net/fcs-vs-battle/images/2/2c/Annoying_Dog_Render.png/revision/latest/scale-to-width-down/340?cb=20180730225500"},
        "NORMAL": {"emoji": "🌳", "color": "0x00FF00", "thumbnail_url": ""}
    }

    data = load_json_data(BIOMES_DATA_FILENAME, default_data, [BIOMES_DATA_FILENAME])

    # Check if we need to add any new biomes from default_data that are missing in user data
    data_updated = False
    for biome, default_info in default_data.items():
        if biome not in data:
            print(f"Adding new biome '{biome}' to biome data configuration.")
            data[biome] = default_info.copy()
            data_updated = True

    # Ensure all biomes have emoji data from default_data
    for biome, info in data.items():
        if biome in default_data and "emoji" not in info:
            info["emoji"] = default_data[biome].get("emoji", "🌍")
        elif "emoji" not in info:
            info["emoji"] = "🌍"  # Default emoji for unknown biomes

        if isinstance(info.get("color"), (int, str)) and not info["color"].startswith("0x"):
            try:
                info["color"] = f"0x{int(info['color']):06X}"
            except (ValueError, TypeError):
                info["color"] = "0xFFFFFF"
        elif not isinstance(info.get("color"), str) or not info["color"].startswith("0x"):
             info["color"] = "0xFFFFFF"

    # Save the updated data if new biomes were added
    if data_updated:
        print("Saving updated biome data with new biomes.")
        save_json_data(BIOMES_DATA_FILENAME, data)

    return data
    
def load_auras_json():
    """Loads auras data."""
    return load_json_data(AURAS_FILENAME, {}, [AURAS_FILENAME])

def load_logs():
    """Loads biome/app logs."""
    legacy_logs_path = 'macro_logs.txt'
    appdata_path = os.path.join(CONFIG_DIR, LOGS_FILENAME)

    if not os.path.exists(appdata_path) and os.path.exists(legacy_logs_path):
        print(f"Found legacy log file at {legacy_logs_path}. Migrating...")
        try:
            with open(legacy_logs_path, 'r', encoding='utf-8') as file:
                lines = file.read().splitlines()

            json_logs = [{"message": line, "timestamp": ""} for line in lines]
            save_json_data(LOGS_FILENAME, json_logs)
            print(f"Migrated logs from {legacy_logs_path} to {appdata_path}")

            return json_logs
        except Exception as e:
            error_logging(e, f"Failed to migrate legacy logs from {legacy_logs_path}. Loading normally.")

    return load_json_data(LOGS_FILENAME, []) 

def save_logs(logs_data):
    """Saves biome/app logs."""

    try:
        sorted_logs = sorted(logs_data, key=lambda x: x.get("timestamp", ""), reverse=True)
        save_json_data(LOGS_FILENAME, sorted_logs)
    except Exception as e:
        error_logging(e, "Failed to sort and save logs.")
        save_json_data(LOGS_FILENAME, logs_data) 

ROBLOX_LOGS_DIR = os.path.join(os.getenv('LOCALAPPDATA'), 'Roblox', 'logs')

log_file_cache = {}
log_file_cache_expiry = 30 

def get_log_files(logs_dir=ROBLOX_LOGS_DIR, silent=False, force_refresh=False):
    """Get Roblox player log files, sorted by modification time (newest first), with caching."""
    global log_file_cache
    current_time = time.time()

    if not force_refresh and 'timestamp' in log_file_cache and (current_time - log_file_cache.get('timestamp', 0) < log_file_cache_expiry):
         if 'paths' in log_file_cache:

              if all(os.path.exists(p) for p in log_file_cache['paths']):

                   return log_file_cache['paths']
              else:
                   print("DEBUG: Some cached paths missing, refreshing.") 

    log_files_details = []
    try:
        if not os.path.exists(logs_dir):
            if not silent: print(f"WARNING: Logs directory not found: {logs_dir}")
            return []

        for filename in os.listdir(logs_dir):
            if not filename.endswith('.log'):
                continue

            is_player_log = "player" in filename.lower() or "_Player_" in filename

            if is_player_log:
                full_path = os.path.join(logs_dir, filename)
                try:
                    if os.path.isfile(full_path):
                        stats = os.stat(full_path)
                        if stats.st_size > 0: 
                            mod_time = stats.st_mtime
                            age_in_seconds = current_time - mod_time

                            priority = 0
                            if age_in_seconds < 300: priority += 2 
                            if "last" in filename.lower(): priority += 1

                            if age_in_seconds < 86400: 
                                log_files_details.append({
                                    'path': full_path,
                                    'mod_time': mod_time,
                                    'age': age_in_seconds,
                                    'priority': priority,
                                    'size': stats.st_size
                                })
                except (OSError, IOError, FileNotFoundError) as e:

                     if not silent: print(f"DEBUG: Skipping file {filename} due to error: {e}")
                     continue

        if not log_files_details:
            return []

        log_files_details.sort(key=lambda x: (-x['priority'], x['age']))

        log_file_cache = {
            'timestamp': current_time,
            'details': log_files_details,
            'paths': [f['path'] for f in log_files_details]
        }

        return log_file_cache['paths']

    except Exception as e:
        error_logging(e, "Error getting log files")
        return []

def get_latest_log_file(logs_dir=ROBLOX_LOGS_DIR):
    """Gets the path to the most relevant (usually most recent 'player...last') log file."""
    log_files = get_log_files(logs_dir, silent=True) 
    if not log_files:
        return None

    return log_files[0]

def apply_roblox_fastflags(update_status_callback=None):
    """Apply Roblox FastFlag settings for logging"""
    local_app_data = os.getenv('LOCALAPPDATA')
    if not local_app_data:
        if update_status_callback:
            update_status_callback("Error: LOCALAPPDATA environment variable not found.")
        return

    required_flags = {
        "FStringDebugLuaLogLevel": "trace",
        "FStringDebugLuaLogPattern": "ExpChat/mountClientApp"
    }
    applied_count = 0
    updated_count = 0

    def update_json_file(json_file_path, launcher_info_str):
        nonlocal applied_count, updated_count
        current_settings = {}
        needs_update = False
        file_existed = False
        file_dir = os.path.dirname(json_file_path)

        try:
            os.makedirs(file_dir, exist_ok=True)

            if os.path.exists(json_file_path):
                file_existed = True
                try:
                    with open(json_file_path, 'r') as f:
                        content = f.read()
                        if content.strip(): 
                            current_settings = json.loads(content)
                        else:
                            current_settings = {} 
                except json.JSONDecodeError:
                    if update_status_callback:
                        update_status_callback(f"Warning: Corrupt JSON found at {json_file_path}. Overwriting for {launcher_info_str}.")
                    current_settings = {}
                    needs_update = True
                except Exception as read_err:
                    if update_status_callback:
                        update_status_callback(f"Warning: Error reading {json_file_path}: {read_err}. Overwriting for {launcher_info_str}.")
                    current_settings = {}
                    needs_update = True
            else:
                needs_update = True

            for key, value in required_flags.items():
                if key not in current_settings or current_settings[key] != value:
                    current_settings[key] = value
                    needs_update = True

            if needs_update:
                with open(json_file_path, 'w') as f:
                    json.dump(current_settings, f, indent=2)
                if file_existed:
                    updated_count += 1
                    if update_status_callback:
                        update_status_callback(f"Updated FastFlags in {launcher_info_str} file")
                else:
                    applied_count += 1
                    if update_status_callback:
                        update_status_callback(f"Applied FastFlags to new file in {launcher_info_str}")

        except Exception as e:
            if update_status_callback:
                update_status_callback(f"Error processing FastFlags for {launcher_info_str}: {e}")

    mod_launchers_config_files = {
        'Bloxstrap': os.path.join(local_app_data, 'Bloxstrap', 'Modifications', 'ClientSettings', 'ClientAppSettings.json'),
        'Fishstrap': os.path.join(local_app_data, 'Fishstrap', 'Modifications', 'ClientSettings', 'ClientAppSettings.json')
    }

    for launcher_name, target_json_path in mod_launchers_config_files.items():
        launcher_base_dir = os.path.dirname(os.path.dirname(os.path.dirname(target_json_path)))
        if os.path.isdir(launcher_base_dir):
            update_json_file(target_json_path, f"{launcher_name} Modifications")

    roblox_versions_path = os.path.join(local_app_data, 'Roblox', 'Versions')
    if os.path.isdir(roblox_versions_path):
        try:
            for item_name in os.listdir(roblox_versions_path):
                item_path = os.path.join(roblox_versions_path, item_name)

                if os.path.isdir(item_path) and item_name.startswith("version-"): # Modified to match user's code
                    version_folder_path = item_path
                    client_settings_path = os.path.join(version_folder_path, 'ClientSettings')
                    json_file_path = os.path.join(client_settings_path, 'ClientAppSettings.json')

                    update_json_file(json_file_path, f"Roblox/{item_name}")
        except OSError as e: # Modified to match user's code
            if update_status_callback:
                update_status_callback(f"Error accessing Roblox versions directory: {e}")

    if applied_count > 0 or updated_count > 0:
        if update_status_callback:
            update_status_callback(f"Finished applying/updating FastFlags ({applied_count} new, {updated_count} updated)." )
    else:
        if update_status_callback:
            update_status_callback("FastFlags check complete. No changes needed or relevant folders found.")

def parse_session_time(session_time_str):
    """Parse session time from H:M:S string format to seconds."""
    try:
        if isinstance(session_time_str, str) and ':' in session_time_str:
            parts = session_time_str.split(':')
            if len(parts) == 3:
                h, m, s = map(int, parts)
                return h * 3600 + m * 60 + s
            elif len(parts) == 2: 
                m, s = map(int, parts)
                return m * 60 + s
    except (ValueError, AttributeError, TypeError) as e:

        print(f"Warning: Could not parse session time string '{session_time_str}'. Error: {e}. Resetting to 0.")
    return 0 

def format_session_time(total_seconds):
    """Format total seconds into H:M:S string."""
    if not isinstance(total_seconds, (int, float)) or total_seconds < 0:
        total_seconds = 0
    total_seconds = int(total_seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def check_for_updates(current_version, repo_url="https://api.github.com/repos/cresqnt-sys/MultiScope/releases"):
    """Checks GitHub releases for a newer version by comparing against the latest tag. Returns release info or None."""
    print(f"Checking for updates... Current version: {current_version}")

    try:
        response = requests.get(repo_url, timeout=10) 
        response.raise_for_status() 
        all_releases = response.json()

        if not all_releases:
            print("No releases found on GitHub.")
            return None

        # Get the latest release (first in the list)
        latest_release_info = all_releases[0]
        latest_tag_name = latest_release_info.get('tag_name', '0.0.0')
        if latest_tag_name.startswith('v'):
            latest_tag_name = latest_tag_name[1:]

        # Add parsed_tag_name to the release info for consistency with how app.py uses it
        latest_release_info['parsed_tag_name'] = latest_tag_name

        if compare_versions(latest_tag_name, current_version) > 0:
            print(f"Update found: {latest_tag_name} (Current: {current_version})")
            return latest_release_info 
        else:
            print("Current version is up to date or newer than the latest tag.")
            return None

    except requests.exceptions.RequestException as e:
        print(f"Update check failed: Network error ({e})")
        return None
    except Exception as e:
        error_logging(e, "Error during update check")
        return None

def compare_versions(version1_str, version2_str):
    """Compares two version strings (e.g., '1.0.5', '1.1.0-Beta1'). Handles pre-release tags simply."""
    def normalize_version(v_str):
        parts = v_str.split('-')[0].split('.')

        numeric_parts = []
        for part in parts:
            try:
                numeric_parts.append(int(part))
            except ValueError:
                numeric_parts.append(0) 
        return numeric_parts

    v1_parts = normalize_version(version1_str)
    v2_parts = normalize_version(version2_str)

    len_diff = len(v1_parts) - len(v2_parts)
    if len_diff < 0:
        v1_parts.extend([0] * abs(len_diff))
    elif len_diff > 0:
        v2_parts.extend([0] * len_diff)

    if v1_parts > v2_parts: return 1
    if v1_parts < v2_parts: return -1

    v1_prerelease = '-' in version1_str
    v2_prerelease = '-' in version2_str

    if not v1_prerelease and v2_prerelease: return 1 
    if v1_prerelease and not v2_prerelease: return -1 

    return 0

def download_update(download_url, root_window):
    """Downloads an update file, showing progress."""
    try:

        file_name = os.path.basename(download_url)
        if not file_name or not file_name.endswith(('.exe', '.zip', '.msi')): 
            file_name = f'{APP_NAME}_Update.exe' 

        save_path = filedialog.asksaveasfilename(
            defaultextension=".exe", 
            filetypes=[("Executable files", "*.exe"), ("Zip archives", "*.zip"), ("All files", "*.*")],
            initialfile=file_name,
            title="Save MultiScope Update As"
        )

        if not save_path:
            print("Update download cancelled by user.")
            return None 

        print(f"Downloading update to: {save_path}")

        progress_window = ttk.Toplevel(root_window)
        progress_window.title("Downloading Update")
        progress_window.geometry("350x150")
        progress_window.transient(root_window) 
        progress_window.grab_set() 
        progress_window.resizable(False, False)

        ttk.Label(progress_window, text="Downloading update...").pack(pady=10)
        progress_bar = ttk.Progressbar(progress_window, length=300, mode='determinate')
        progress_bar.pack(pady=10)
        size_label = ttk.Label(progress_window, text="0 MB / 0 MB (0%)")
        size_label.pack(pady=5)
        progress_window.update_idletasks() 

        response = requests.get(download_url, stream=True, timeout=30) 
        response.raise_for_status()

        total_size = int(response.headers.get('content-length', 0))
        downloaded_size = 0
        block_size = 8192 

        with open(save_path, 'wb') as f:
            for data in response.iter_content(block_size):
                f.write(data)
                downloaded_size += len(data)

                if total_size > 0:
                    percentage = (downloaded_size / total_size) * 100
                    progress_bar['value'] = percentage
                    size_label.config(text=f"{downloaded_size/1024/1024:.1f} MB / {total_size/1024/1024:.1f} MB ({percentage:.1f}%)")
                else: 
                     progress_bar['mode'] = 'indeterminate'
                     progress_bar.start()
                     size_label.config(text=f"{downloaded_size/1024/1024:.1f} MB downloaded")

                progress_window.update() 

        progress_window.destroy()
        print("Update downloaded successfully.")
        return save_path 

    except requests.exceptions.RequestException as e:
        messagebox.showerror("Download Failed", f"Failed to download update: {str(e)}", parent=root_window)
        error_logging(e, "Failed to download update")
        if 'progress_window' in locals() and progress_window.winfo_exists(): progress_window.destroy()
        return None
    except Exception as e:
        messagebox.showerror("Error", f"An error occurred during download: {str(e)}", parent=root_window)
        error_logging(e, "Error downloading update")
        if 'progress_window' in locals() and progress_window.winfo_exists(): progress_window.destroy()
        return None

def setup_locale():
    """Sets the application locale, trying common fallbacks."""
    common_locales = ['en_US.UTF-8', 'en_US', 'C', ''] 
    for loc in common_locales:
        try:
            locale.setlocale(locale.LC_ALL, loc)
            print(f"Locale set to: {locale.getlocale()}")
            return True
        except locale.Error:
            continue
    print("Warning: Could not set a suitable locale. Using system default or POSIX 'C'.")

    try:
        locale.setlocale(locale.LC_ALL, '')
    except locale.Error as e:
         print(f"FATAL: Could not set any locale. Error: {e}")

    return False

class ToolTip:
    """
    Create a tooltip for a given widget.
    """
    def __init__(self, widget, text='widget info'):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.id = None
        self.x = self.y = 0
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)
        self.widget.bind("<ButtonPress>", self.leave) 

    def enter(self, event=None):
        self.schedule()

    def leave(self, event=None):
        self.unschedule()
        self.hidetip()

    def schedule(self):
        self.unschedule()
        self.id = self.widget.after(500, self.showtip) 

    def unschedule(self):
        id_ = self.id
        self.id = None
        if id_:
            self.widget.after_cancel(id_)

    def showtip(self, event=None):
        x, y, _, _ = self.widget.bbox("insert") 
        x += self.widget.winfo_rootx() + 25 
        y += self.widget.winfo_rooty() + 20

        self.tooltip_window = tk.Toplevel(self.widget)

        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{x}+{y}")

        try:
            style = ttk.Style.get_instance()
            bg = style.lookup('Tooltip.TLabel', 'background', default='lightyellow')
            fg = style.lookup('Tooltip.TLabel', 'foreground', default='black')
            relief = style.lookup('Tooltip.TLabel', 'relief', default='solid')
            borderwidth = style.lookup('Tooltip.TLabel', 'borderwidth', default=1)
            font = style.lookup('Tooltip.TLabel', 'font') 

            label = ttk.Label(self.tooltip_window, text=self.text, justify='left',
                              background=bg, foreground=fg, relief=relief, borderwidth=borderwidth,
                              padding=(5, 2), font=font)
        except: 
             label = tk.Label(self.tooltip_window, text=self.text, justify='left',
                             background="#ffffe0", relief='solid', borderwidth=1,
                             font=("tahoma", "8", "normal"))

        label.pack(ipadx=1)

    def hidetip(self):
        tw = self.tooltip_window
        self.tooltip_window = None
        if tw:
            tw.destroy()

def create_tooltip(widget, text):
    """Factory function to easily create tooltips."""

    if not hasattr(widget, "_tooltip_handler"):
         widget._tooltip_handler = ToolTip(widget, text)
    else:

         widget._tooltip_handler.text = text

def get_ps_link_for_user(username, accounts_list, default_link=""):
    """Gets the private server link for a user from the accounts list."""
    if not username or not accounts_list:
        return default_link
    username_lower = username.lower()
    for account in accounts_list:
        if account.get("username", "").lower() == username_lower:
            return account.get("ps_link", default_link) 
    return default_link 
