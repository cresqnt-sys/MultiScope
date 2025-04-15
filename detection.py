import os
import re
import time
import json
import requests
import concurrent.futures
import psutil
from datetime import datetime, timedelta

from utils import error_logging, get_log_files, load_biome_data, ROBLOX_LOGS_DIR, compare_versions

DEFAULT_WEBHOOK_RATE_LIMIT = 1.0 
RPC_CACHE_MAX_SIZE = 200
LOG_READ_SIZE = 50000 
LOG_READ_CHUNK_SIZE = 2000 
ACTIVE_LOG_THRESHOLD = 300 
STALE_LOG_THRESHOLD = 300 

class DetectionManager:
    def __init__(self, app_instance):
        """Initialize the Detection Manager.

        Args:
            app_instance: The main application instance (e.g., MultiScopeApp)
                          to access shared state like config, accounts, logs etc.
        """
        self.app = app_instance 
        self.biome_data = load_biome_data() 

        self.account_biomes = {} 
        self.account_last_positions = {} 
        self.account_last_sent_webhook = {} 
        self.account_last_timestamp = {} 
        self.username_log_cache = {} 
        self.locked_log_files = {} 
        self.player_added_verified_logs = set() 
        self.log_file_update_times = {} 
        self.log_file_size_cache = {} 
        self.rpc_message_cache = {} 
        self.rpc_raw_cache = {} 
        self.rpc_raw_cache_keys = [] 
        self.sent_webhooks_cache = set() 
        self.last_webhook_time = 0 
        self.webhook_rate_limit = DEFAULT_WEBHOOK_RATE_LIMIT 
        self.last_roblox_process_count = -1 
        self.last_log_check_message_time = {} 
        self.last_scan_times = {} 
        self.last_player_detection_time = {} 
        self.last_full_scan_time = 0 
        self.log_scan_count = 0 

        self._initialize_account_states()

    def _initialize_account_states(self):
        """Initialize detection state for accounts present in the app config."""
        if not hasattr(self.app, 'accounts'): return

        usernames = [acc.get("username") for acc in self.app.accounts if acc.get("username")]
        now_min = datetime.min

        for username in usernames:
            if username not in self.account_biomes:
                self.account_biomes[username] = None
            if username not in self.account_last_positions:
                self.account_last_positions[username] = 0
            if username not in self.account_last_sent_webhook:
                 self.account_last_sent_webhook[username] = {biome: now_min for biome in self.biome_data}
            if username not in self.account_last_timestamp:

                 start_time_iso = getattr(self.app, 'program_start_time_iso', "1970-01-01T00:00:00")
                 self.account_last_timestamp[username] = start_time_iso

        active_usernames = set(usernames)
        for state_dict in [self.account_biomes, self.account_last_positions, self.account_last_sent_webhook, self.account_last_timestamp, self.username_log_cache, self.locked_log_files, self.last_log_check_message_time, self.last_player_detection_time]:
            for user in list(state_dict.keys()):
                if user not in active_usernames:
                    del state_dict[user]

    def reset_detection_states(self):
        """Resets detection-specific states when detection starts/restarts."""
        print("Resetting detection states...")
        self.account_biomes.clear()
        self.account_last_positions.clear()
        self.account_last_sent_webhook.clear()
        self.account_last_timestamp.clear()
        self.username_log_cache.clear()
        self.locked_log_files.clear()
        self.player_added_verified_logs.clear()

        self.rpc_message_cache.clear()
        self.rpc_raw_cache.clear()
        self.rpc_raw_cache_keys.clear()
        self.sent_webhooks_cache.clear()
        self.last_webhook_time = 0
        self.webhook_rate_limit = DEFAULT_WEBHOOK_RATE_LIMIT
        self.last_roblox_process_count = -1
        self.last_log_check_message_time.clear()
        self.last_scan_times.clear()
        self.last_player_detection_time.clear()
        self.last_full_scan_time = 0
        self.log_scan_count = 0

        self._initialize_account_states()

    def get_active_roblox_count(self):
        """Counts active RobloxPlayerBeta.exe processes."""
        count = 0
        try:
            for proc in psutil.process_iter(['name']):

                if proc.info['name'] and proc.info['name'].lower() == 'robloxplayerbeta.exe':
                    count += 1

            if count != self.last_roblox_process_count:
                 self.app.append_log(f"Detected {count} active Roblox instances via psutil.")
                 self.last_roblox_process_count = count
            return count
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):

            return self.last_roblox_process_count 
        except Exception as e:
            error_logging(e, "Error counting Roblox processes")
            return self.last_roblox_process_count 

    def _get_active_log_files(self, all_log_files):
        """Filters log files to find those modified within the active threshold."""
        active_files = []
        current_time = time.time()
        for log_file in all_log_files:
            try:

                last_mod_time = self.log_file_update_times.get(log_file)
                if last_mod_time is None or current_time - last_mod_time > 5: 
                     if not os.path.exists(log_file): continue 
                     last_mod_time = os.path.getmtime(log_file)
                     self.log_file_update_times[log_file] = last_mod_time

                if current_time - last_mod_time < ACTIVE_LOG_THRESHOLD:
                    active_files.append(log_file)
            except FileNotFoundError:
                 continue 
            except Exception as e:
                error_logging(e, f"Error checking modification time for {log_file}")
        return active_files

    def scan_for_player_added_messages(self, all_log_files):
        """Scan log files for "Player added" messages to identify accounts and associate logs."""
        newly_found_accounts = []
        if not hasattr(self.app, 'accounts'): return newly_found_accounts

        self.log_scan_count += 1
        current_time = time.time()

        logs_to_scan = []
        for log_file in all_log_files:
            try:
                if current_time - os.path.getmtime(log_file) < ACTIVE_LOG_THRESHOLD:
                    last_scan = self.last_scan_times.get(log_file, 0)
                    if current_time - last_scan > 10: 
                        logs_to_scan.append(log_file)
                        self.last_scan_times[log_file] = current_time
            except Exception:
                continue

        self.last_scan_times = {k: v for k, v in self.last_scan_times.items()
                              if current_time - v < STALE_LOG_THRESHOLD * 2 and os.path.exists(k)}

        if not logs_to_scan:

            return newly_found_accounts

        configured_usernames_lower = {acc.get("username", "").lower() for acc in self.app.accounts if acc.get("username")}

        for log_file in logs_to_scan:
            try:
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as file:

                    content = file.read(LOG_READ_SIZE)

                player_added_regex = r"Player added:\s*(\w+)"
                load_failed_regex = r"load failed in Players\.(\w+)"

                found_players_in_log = set()

                for match in re.finditer(player_added_regex, content, re.IGNORECASE):
                    player_name = match.group(1)
                    if player_name:
                        found_players_in_log.add(player_name)
                        self._process_detected_player(player_name, log_file, configured_usernames_lower, newly_found_accounts, "Player added")

                if not found_players_in_log:
                     for match in re.finditer(load_failed_regex, content, re.IGNORECASE):
                         player_name = match.group(1)
                         if player_name:
                              found_players_in_log.add(player_name)
                              self._process_detected_player(player_name, log_file, configured_usernames_lower, newly_found_accounts, "Load failed")

                if found_players_in_log:
                     self.player_added_verified_logs.add(log_file)

            except FileNotFoundError:

                if log_file in self.last_scan_times: del self.last_scan_times[log_file]
                continue
            except Exception as e:
                error_logging(e, f"Error processing log file for player detection: {log_file}")
                continue

        return newly_found_accounts

    def _process_detected_player(self, player_name, log_file, configured_usernames_lower, newly_found_accounts, detection_method):
        """Helper function to process a player detected in a log file."""
        player_name_lower = player_name.lower()
        current_time = time.time()

        last_detection_log_time = self.last_player_detection_time.get(player_name_lower, 0)
        if current_time - last_detection_log_time > 30:
            self.app.append_log(f"🎮 PLAYER DETECTED: Found '{player_name}' in {os.path.basename(log_file)} via '{detection_method}'")
            self.last_player_detection_time[player_name_lower] = current_time

        self.username_log_cache[player_name] = log_file
        if detection_method == "Player added": 
            self.locked_log_files[player_name] = log_file

        self.app.active_accounts.add(player_name_lower)

        account_found_in_config = False
        for account in self.app.accounts:
            if account.get("username", "").lower() == player_name_lower:
                account_found_in_config = True
                if not account.get("active", True):
                    account["active"] = True
                    self.app.append_log(f"🔄 Reactivated account: {player_name}")

                    self.app.config_changed = True
                break

        if not account_found_in_config:

            if player_name_lower not in configured_usernames_lower and current_time - last_detection_log_time > 300: 
                self.app.append_log(f"ℹ️ Detected active player '{player_name}' not in configuration.")

    def assign_log_files_to_accounts(self, accounts_to_check, active_log_files, current_roblox_count):
        """Attempts to assign active log files to configured accounts."""
        log_files_to_process = {}
        checked_log_files = set() 

        current_time = time.time()
        for username, locked_file in list(self.locked_log_files.items()):
            if username not in [acc.get("username") for acc in accounts_to_check]:

                 del self.locked_log_files[username]
                 continue
            if locked_file in active_log_files and os.path.exists(locked_file):
                 try:
                     if current_time - os.path.getmtime(locked_file) < STALE_LOG_THRESHOLD:
                         log_files_to_process[username] = locked_file
                         checked_log_files.add(locked_file)

                         continue 
                     else:

                         del self.locked_log_files[username]
                         if username in self.username_log_cache and self.username_log_cache[username] == locked_file:
                              del self.username_log_cache[username]
                 except FileNotFoundError:

                      if username in self.locked_log_files: del self.locked_log_files[username]
                      if username in self.username_log_cache and self.username_log_cache[username] == locked_file:
                           del self.username_log_cache[username]
            else:

                 if username in self.locked_log_files: del self.locked_log_files[username]

        for username, cached_file in list(self.username_log_cache.items()):
             if username in log_files_to_process: continue 
             if username not in [acc.get("username") for acc in accounts_to_check]:

                  del self.username_log_cache[username]
                  continue

             if cached_file in active_log_files and os.path.exists(cached_file):
                 try:
                     if current_time - os.path.getmtime(cached_file) < STALE_LOG_THRESHOLD:
                         if cached_file not in checked_log_files:
                             log_files_to_process[username] = cached_file
                             checked_log_files.add(cached_file)

                     else:

                         del self.username_log_cache[username]
                 except FileNotFoundError:

                      if username in self.username_log_cache: del self.username_log_cache[username]
             else:

                 if username in self.username_log_cache: del self.username_log_cache[username]

        remaining_accounts = [acc for acc in accounts_to_check if acc.get("username") not in log_files_to_process]
        available_log_files = [log for log in active_log_files if log not in checked_log_files]

        if len(remaining_accounts) == 1 and len(available_log_files) == 1:
            username = remaining_accounts[0].get("username")
            log_file = available_log_files[0]
            log_files_to_process[username] = log_file
            checked_log_files.add(log_file)
            self.username_log_cache[username] = log_file 
            self.app.append_log(f"Tentatively assigned remaining log {os.path.basename(log_file)} to remaining account {username}")

        return log_files_to_process

    def check_all_accounts_biomes(self):
        """Main loop function to check biomes for all active accounts."""
        try:

            accounts_to_check = [acc for acc in self.app.accounts if acc.get("active", True) and acc.get("username")]
            if not accounts_to_check:

                return

            current_roblox_count = self.get_active_roblox_count()

            num_potential_logs = max(current_roblox_count, len(accounts_to_check))

            all_log_files = get_log_files(silent=True)
            if not all_log_files:

                 return

            current_time = time.time()
            if current_time - self.last_full_scan_time >= 30: 
                self.last_full_scan_time = current_time
                newly_found = self.scan_for_player_added_messages(all_log_files)
                if newly_found:
                     self.app.append_log(f"Found new accounts during periodic scan: {newly_found}")

                     accounts_to_check = [acc for acc in self.app.accounts if acc.get("active", True) and acc.get("username")]

            active_log_files = self._get_active_log_files(all_log_files)

            log_files_to_process = self.assign_log_files_to_accounts(accounts_to_check, active_log_files, num_potential_logs)

            if not log_files_to_process:

                return

            detected_biomes = {}
            max_workers = max(1, min(8, len(log_files_to_process))) 

            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_username = {
                    executor.submit(self.check_single_account_log, username, log_file):
                    username for username, log_file in log_files_to_process.items()
                 }
                for future in concurrent.futures.as_completed(future_to_username):
                    username = future_to_username[future]
                    try:

                        future.result() 
                    except Exception as e:

                         error_logging(e, f"Error in thread processing log for {username}")

        except Exception as e:
            error_logging(e, "Error in check_all_accounts_biomes")

    def check_single_account_log(self, username, log_file_path):
        """Checks a single log file for biome updates for a specific account."""
        try:
            current_time = time.time()

            last_msg_time = self.last_log_check_message_time.get(username, 0)

            if not os.path.exists(log_file_path):

                 if username in self.username_log_cache and self.username_log_cache[username] == log_file_path:
                     del self.username_log_cache[username]
                 if username in self.locked_log_files and self.locked_log_files[username] == log_file_path:
                     del self.locked_log_files[username]
                 return

            try:
                current_size = os.path.getsize(log_file_path)
                current_mod_time = os.path.getmtime(log_file_path)
            except FileNotFoundError:
                 return 
            except Exception as e:
                 error_logging(e, f"Error getting stats for log file {log_file_path}")
                 return

            cached_size = self.log_file_size_cache.get(log_file_path)
            cached_mod_time = self.log_file_update_times.get(log_file_path)

            self.log_file_size_cache[log_file_path] = current_size
            self.log_file_update_times[log_file_path] = current_mod_time

            if cached_size == current_size and cached_mod_time == current_mod_time:

                 return

            if current_size == 0: return 

            last_pos = self.account_last_positions.get(username, 0)
            if last_pos > current_size or cached_size is None or current_size < cached_size:

                read_start_pos = max(0, current_size - LOG_READ_SIZE) 

                self.account_last_timestamp[username] = getattr(self.app, 'program_start_time_iso', "1970-01-01T00:00:00")
            else:
                read_start_pos = last_pos

            new_content = ""
            if read_start_pos < current_size:
                 try:
                     with open(log_file_path, 'r', encoding='utf-8', errors='ignore') as file:
                         file.seek(read_start_pos)

                         new_content = file.read(LOG_READ_CHUNK_SIZE * 10) 
                         self.account_last_positions[username] = file.tell()
                 except FileNotFoundError:
                     return 
                 except Exception as e:
                     error_logging(e, f"Error reading log file {log_file_path} for {username}")
                     return
            else:

                self.account_last_positions[username] = current_size
                return

            if not new_content:
                 return

            last_processed_timestamp = self.account_last_timestamp.get(username, "1970-01-01T00:00:00")
            new_last_timestamp = last_processed_timestamp
            detected_biome_in_chunk = None

            lines = new_content.splitlines()
            for line in lines:
                try:

                    timestamp_match = re.match(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})', line)
                    if not timestamp_match: continue
                    timestamp = timestamp_match.group(1)

                    if timestamp <= last_processed_timestamp: continue

                    if timestamp > new_last_timestamp:
                        new_last_timestamp = timestamp

                    if "[BloxstrapRPC]" in line:
                        biome = self.get_biome_from_rpc(line)
                        if biome:
                            detected_biome_in_chunk = biome

                            continue 

                    if detected_biome_in_chunk is None:
                        line_upper = line.upper()

                        noise_patterns = ["[WARNING]", "[ERROR]", "[INFO]", "[DEBUG]", "HTTP", "TEXTURE", "SOUND", "REQUEST", "DEPRECATED"]
                        has_noise = any(noise in line_upper for noise in noise_patterns)
                        biome_keywords = ["BIOME", "ENTERED", "CURRENT", "ENVIRONMENT", "LOCATION"]
                        has_biome_keyword = any(key in line_upper for key in biome_keywords)

                        if has_noise and not has_biome_keyword: continue

                        for biome_name in self.biome_data:
                            biome_upper = biome_name.upper()

                            patterns = [
                                rf"\bBIOME:\s*{re.escape(biome_upper)}\b",
                                rf"\bBIOME\s+{re.escape(biome_upper)}\b",
                                rf"\bENTERED\s+{re.escape(biome_upper)}\b",
                                rf"\bCURRENT BIOME:\s*{re.escape(biome_upper)}\b",
                                rf"\bCURRENT BIOME\s+{re.escape(biome_upper)}\b",
                                rf"\bBIOME CHANGED TO\s*{re.escape(biome_upper)}\b",
                                rf"\bBIOME CHANGED:\s*{re.escape(biome_upper)}\b",
                                rf"\bBIOME TYPE:\s*{re.escape(biome_upper)}\b",
                                rf"\bENVIRONMENT:\s*{re.escape(biome_upper)}\b",

                            ]
                            if any(re.search(p, line_upper) for p in patterns):
                                detected_biome_in_chunk = biome_name

                                break 

                except Exception as line_error:
                    error_logging(line_error, f"Error processing line for {username}: {line[:100]}...")
                    continue

            if new_last_timestamp > last_processed_timestamp:
                 self.account_last_timestamp[username] = new_last_timestamp

            if detected_biome_in_chunk:
                 self.handle_account_biome_detection(username, detected_biome_in_chunk)

        except Exception as e:
            error_logging(e, f"Error in check_single_account_log for {username}")

    def handle_account_biome_detection(self, username, biome):
        """Handles the logic when a new biome is detected for an account."""
        if not username or not biome or biome not in self.biome_data:
            print(f"Warning: Invalid arguments for handle_account_biome_detection ({username}, {biome})")
            return

        current_biome = self.account_biomes.get(username)
        previous_biome = current_biome 

        if biome == current_biome:

            return

        self.app.append_log(f"🌍 Biome change for {username}: {previous_biome or 'None'} -> {biome}")
        self.account_biomes[username] = biome
        now = datetime.now()

        if username not in self.account_last_sent_webhook: self.account_last_sent_webhook[username] = {}
        self.account_last_sent_webhook[username][biome] = now 

        if hasattr(self.app, 'biome_counts'):
            self.app.biome_counts[biome] = self.app.biome_counts.get(biome, 0) + 1

            if self.app.biome_counts[biome] % 5 == 0:
                 self.app.config_changed = True 

        message_type = self.app.config.get("biome_notifier", {}).get(biome, "Message") 
        notification_enabled = self.app.config.get("biome_notification_enabled", {}).get(biome, True)

        if biome in ["GLITCHED", "DREAMSPACE"]:
            message_type = "Ping" 
            notification_enabled = True 

        webhook_tasks = []

        if previous_biome and previous_biome in self.biome_data:
            prev_message_type = self.app.config.get("biome_notifier", {}).get(previous_biome, "Message")
            prev_notification_enabled = self.app.config.get("biome_notification_enabled", {}).get(previous_biome, True)
            if previous_biome in ["GLITCHED", "DREAMSPACE"]: 
                prev_message_type = "Message" 
                prev_notification_enabled = True

            if prev_message_type != "None" and prev_notification_enabled:
                webhook_tasks.append(("end", previous_biome, prev_message_type))

        if message_type != "None" and notification_enabled:
            webhook_tasks.append(("start", biome, message_type))

        for event_type, biome_name, msg_type in webhook_tasks:
             self.send_account_webhook(username, biome_name, msg_type, event_type)

    def get_biome_from_rpc(self, rpc_message):
        """Extract biome name from Bloxstrap RPC message using cache."""

        if rpc_message in self.rpc_raw_cache:
            return self.rpc_raw_cache[rpc_message]

        message_parts = []
        for part in ["largeImage", "details", "state"]:
            if part in rpc_message:
                start_idx = rpc_message.find(part)

                colon_idx = rpc_message.find(':', start_idx)
                if colon_idx > start_idx:
                    val_start_idx = colon_idx + 1

                    comma_idx = rpc_message.find(',', val_start_idx)
                    brace_idx = rpc_message.find('}', val_start_idx)
                    end_idx = -1
                    if comma_idx != -1 and brace_idx != -1:
                         end_idx = min(comma_idx, brace_idx)
                    elif comma_idx != -1:
                         end_idx = comma_idx
                    elif brace_idx != -1:
                         end_idx = brace_idx

                    if end_idx > val_start_idx:
                         value = rpc_message[val_start_idx:end_idx].strip().strip('"''')
                         message_parts.append(f"{part}:{value}")
                    elif val_start_idx < len(rpc_message): 
                         value = rpc_message[val_start_idx:].strip().strip('"''}')
                         message_parts.append(f"{part}:{value}")

        message_hash = hash(":".join(message_parts))
        if message_hash in self.rpc_message_cache:

            biome = self.rpc_message_cache[message_hash]
            self._add_to_rpc_raw_cache(rpc_message, biome)
            return biome

        found_biome = None

        potential_biome_strings = []
        for part in ["largeImage", "details", "state"]:

             match = re.search(fr"\"{part}\"\s*:\s*\"([^\"]+)\"|'{part}'\s*:\s*'([^']+)'", rpc_message)
             if match:

                 value = match.group(1) if match.group(1) is not None else match.group(2)
                 potential_biome_strings.append(value)

        for biome_str in potential_biome_strings:
            biome_str_upper = biome_str.upper()

            for biome_name in self.biome_data:
                if biome_name.upper() == biome_str_upper:
                    found_biome = biome_name
                    break
            if found_biome: break

            if not found_biome:
                 for biome_name in self.biome_data:
                      if biome_name.upper() in biome_str_upper:
                           found_biome = biome_name
                           break
            if found_biome: break

        if not found_biome:
             rpc_upper = rpc_message.upper()

             for biome_name in self.biome_data:

                  if re.search(rf'\b{re.escape(biome_name.upper())}\b', rpc_upper):
                       found_biome = biome_name
                       break

        self.rpc_message_cache[message_hash] = found_biome
        self._add_to_rpc_raw_cache(rpc_message, found_biome)

        return found_biome

    def _add_to_rpc_raw_cache(self, message, biome):
        """Adds an entry to the raw RPC cache, managing size."""
        if len(self.rpc_raw_cache) >= RPC_CACHE_MAX_SIZE:
            try:
                oldest_key = self.rpc_raw_cache_keys.pop(0)
                del self.rpc_raw_cache[oldest_key]
            except (IndexError, KeyError):

                 keys_to_remove = list(self.rpc_raw_cache.keys())[:RPC_CACHE_MAX_SIZE // 10]
                 for key in keys_to_remove:
                     del self.rpc_raw_cache[key]
                 self.rpc_raw_cache_keys = list(self.rpc_raw_cache.keys()) 
        self.rpc_raw_cache[message] = biome
        self.rpc_raw_cache_keys.append(message)

    def send_account_webhook(self, username, biome, message_type, event_type):
        """Sends a webhook notification for a specific account's biome event."""
        webhooks_config = self.app.config.get("webhooks", [])
        if not webhooks_config: return
        if message_type == "None": return

        notification_key = f"{username.lower()}_{biome}_{event_type}_{int(time.time() // 2)}" 
        if notification_key in self.sent_webhooks_cache:

             return
        self.sent_webhooks_cache.add(notification_key)

        if len(self.sent_webhooks_cache) > 100:

             self.sent_webhooks_cache = set(list(self.sent_webhooks_cache)[-100:])

        current_time = time.time()
        time_since_last = current_time - self.last_webhook_time
        if time_since_last < self.webhook_rate_limit:
            sleep_time = self.webhook_rate_limit - time_since_last
            self.app.append_log(f"⏳ Rate limiting webhook ({username}/{biome}), waiting {sleep_time:.2f}s")
            time.sleep(sleep_time)
        self.last_webhook_time = time.time() 

        biome_info = self.biome_data.get(biome, {})
        try:

            biome_color = int(biome_info.get("color", "0xFFFFFF").replace("0x", ""), 16)
        except ValueError:
             biome_color = 0xFFFFFF 

        unix_timestamp = int(time.time())
        timestamp_full = f"<t:{unix_timestamp}:F>"
        timestamp_relative = f"<t:{unix_timestamp}:R>"
        icon_url = biome_info.get("thumbnail_url") or "https://i.postimg.cc/mDzwFfX1/GLITCHED.png" 

        original_username = username
        for account in self.app.accounts:
            if account.get("username", "").lower() == username.lower():
                original_username = account.get("username")
                break

        ps_link = self.app.get_ps_link_for_user(username) 

        content = ""
        user_id_to_ping = None
        if event_type == "start":
             if biome in ["GLITCHED", "DREAMSPACE"]:
                 content = "@everyone"

             elif message_type == "Ping":

                  pass 

        biome_emoji = biome_info.get("emoji", "🌍")
        title = f"{biome_emoji} {biome} Biome Started" if event_type == "start" else f"{biome_emoji} {biome} Biome Ended"

        description = f"**Account:** `{original_username}`\n"
        description += f"**Time:** {timestamp_full} ({timestamp_relative})\n"

        if event_type == "start":
            description += f"**Private Server:** {ps_link if ps_link else 'N/A'}\n"
            description += f"**Status:** Active ✅\n"
        else:
            description += f"**Status:** Ended ⏹️\n"

        if "description" in biome_info and biome_info["description"]:
             description += f"\n* {biome_info['description']}*\n"

        embed = {
            "title": title,
            "description": description,
            "color": biome_color,
            "footer": {
                "text": f"MultiScope | v{self.app.version}",
                "icon_url": "https://i.postimg.cc/mDzwFfX1/GLITCHED.png"
            },

        }
        if icon_url:
            embed["thumbnail"] = {"url": icon_url}

        sent_successfully_to_any = False
        sent_urls = set()
        for webhook_entry in webhooks_config:
            webhook_url = webhook_entry.get("url", "").strip()
            if not webhook_url or webhook_url in sent_urls: continue

            account_notifications = webhook_entry.get("account_notifications") 
            notify_all = account_notifications is None or not account_notifications

            if notify_all or (username.lower() in [acc.lower() for acc in account_notifications]):
                try:

                    ping_content = content
                    webhook_user_id = webhook_entry.get("user_id") 
                    if message_type == "Ping" and webhook_user_id and not ping_content.startswith("@everyone"):
                         ping_content = f"<@{webhook_user_id}> {ping_content}".strip()

                    response = requests.post(
                        webhook_url,
                        json={
                            "content": ping_content,
                            "embeds": [embed]
                        },
                        headers={"Content-Type": "application/json"},
                        timeout=10
                    )
                    response.raise_for_status()
                    self.app.append_log(f"✅ Webhook sent for {original_username}/{biome}/{event_type} to URL ending in ...{webhook_url[-10:]}")
                    sent_successfully_to_any = True
                    sent_urls.add(webhook_url)

                    time.sleep(0.3)
                except requests.exceptions.RequestException as e:
                    error_logging(e, f"Failed to send webhook for {original_username} to URL ending in ...{webhook_url[-10:]}")

                    if response is not None and response.status_code == 429:

                        self.webhook_rate_limit = min(self.webhook_rate_limit + 0.5, 5.0)
                        self.app.append_log(f"Discord rate limit hit. Increased delay to {self.webhook_rate_limit:.1f}s")
                        time.sleep(1.5) 
                except Exception as e:
                     error_logging(e, f"Unexpected error sending webhook for {original_username} to URL ending in ...{webhook_url[-10:]}")

        if sent_successfully_to_any and self.webhook_rate_limit > DEFAULT_WEBHOOK_RATE_LIMIT:
             self.webhook_rate_limit = max(DEFAULT_WEBHOOK_RATE_LIMIT, self.webhook_rate_limit - 0.1)

    def test_webhook(self, webhook_url):
        """Sends a test message to the specified webhook URL."""
        if not webhook_url:
            self.app.show_message_box("Error", "Webhook URL is empty.", "error")
            return False

        test_embed = {
            "title": "🧪 Webhook Test Successful 🧪",
            "description": f"This webhook URL is configured correctly in MultiScope v{self.app.version}.",
            "color": 0x00FF00, 
            "footer": {"text": f"MultiScope Test"}
        }
        try:
            response = requests.post(
                webhook_url,
                json={"content": "MultiScope Test", "embeds": [test_embed]},
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            response.raise_for_status()
            self.app.show_message_box("Success", "Test message sent successfully!", "info")
            self.app.append_log(f"Test webhook successful for URL ending in ...{webhook_url[-10:]}")
            return True
        except requests.exceptions.RequestException as e:
            error_msg = f"Webhook test failed: {e}"

            if response is not None:
                 if response.status_code == 404: error_msg += "\n(Webhook URL not found)"
                 elif response.status_code == 401: error_msg += "\n(Unauthorized - Invalid URL?)"
                 elif response.status_code == 400: error_msg += "\n(Bad request - Embed format issue?)"
            self.app.show_message_box("Error", error_msg, "error")
            error_logging(e, f"Failed to send test webhook to ...{webhook_url[-10:]}")
            return False
        except Exception as e:
             error_logging(e, f"Unexpected error testing webhook ...{webhook_url[-10:]}")
             self.app.show_message_box("Error", f"An unexpected error occurred: {e}", "error")
             return False

    def get_user_activity_data(self, username, days_back=30):
        """Retrieve and process activity data for a specific user from their log file."""
        try:
            self.app.append_log(f"Getting activity data for {username}, looking back {days_back} days")

            log_file = self.get_log_file_for_user(username)
            if not log_file:

                return {'success': False, 'message': f"No log file assigned to {username}."}

            end_date = datetime.now()
            start_date = end_date - timedelta(days=days_back)

            activity = {
                'daily': { (start_date + timedelta(days=i)).strftime('%Y-%m-%d') : {'count': 0, 'actions': {}} for i in range(days_back + 1) },
                'total_actions': 0,
                'action_types': {},
                'first_ts': None,
                'last_ts': None,
            }

            line_count = 0
            processed_count = 0
            with open(log_file, 'r', encoding='utf-8', errors='ignore') as file:
                for line in file:
                    line_count += 1
                    try:

                        ts_match = re.match(r'^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.?\d*)', line)
                        if not ts_match: continue

                        timestamp_str = ts_match.group(1).split('.')[0] 
                        timestamp = datetime.strptime(timestamp_str, '%Y-%m-%dT%H:%M:%S')

                        if timestamp < start_date or timestamp > end_date: continue

                        processed_count += 1
                        date_str = timestamp.strftime('%Y-%m-%d')

                        line_lower = line.lower()
                        action = "Other"
                        if "biome change" in line_lower or "biome detected" in line_lower: action = "Biome"
                        elif "webhook sent" in line_lower: action = "Webhook"
                        elif "antiafk" in line_lower: action = "AntiAFK"
                        elif "player detected" in line_lower: action = "Player ID"
                        elif "starting detection" in line_lower or "stopping detection" in line_lower: action = "Control"
                        elif "error" in line_lower or "failed" in line_lower: action = "Error"

                        activity['total_actions'] += 1
                        activity['action_types'][action] = activity['action_types'].get(action, 0) + 1

                        if date_str in activity['daily']:
                            activity['daily'][date_str]['count'] += 1
                            activity['daily'][date_str]['actions'][action] = activity['daily'][date_str]['actions'].get(action, 0) + 1

                        if activity['first_ts'] is None or timestamp < activity['first_ts']:
                            activity['first_ts'] = timestamp
                        if activity['last_ts'] is None or timestamp > activity['last_ts']:
                            activity['last_ts'] = timestamp

                    except Exception as line_err:

                        pass

            active_days = sum(1 for day_data in activity['daily'].values() if day_data['count'] > 0)

            score = min(100, (activity['total_actions'] / (days_back * 2)) * 50 + (active_days / days_back) * 50)

            result_data = {
                'username': username,
                'log_file': os.path.basename(log_file),
                'days_back': days_back,
                'total_actions': activity['total_actions'],
                'active_days': active_days,
                'action_types': activity['action_types'],
                'daily_activity': activity['daily'],
                'first_activity': activity['first_ts'].strftime('%Y-%m-%d %H:%M:%S') if activity['first_ts'] else 'N/A',
                'last_activity': activity['last_ts'].strftime('%Y-%m-%d %H:%M:%S') if activity['last_ts'] else 'N/A',
                'activity_score': round(score),
                'lines_total': line_count,
                'lines_processed': processed_count
            }

            self.app.append_log(f"Processed activity data for {username}: {processed_count} relevant entries found.")
            return {'success': True, 'message': 'Activity data processed.', 'data': result_data}

        except FileNotFoundError:
             return {'success': False, 'message': f"Log file not found for {username} at path: {log_file}"}
        except Exception as e:
            error_logging(e, f"Error getting activity data for {username}")
            return {'success': False, 'message': f"An error occurred: {e}"}