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
LOG_READ_SIZE = 1048576
LOG_TAIL_READ_BYTES = 2 * 1024 * 1024
LOG_READ_CHUNK_SIZE = 2000 
ACTIVE_LOG_THRESHOLD = 300 
STALE_LOG_THRESHOLD = 300 
LOG_ARRAY_UPDATE_INTERVAL = 60 

class DetectionManager:
    def __init__(self, app_instance):
        """Initialize the Detection Manager.

        Args:
            app_instance: The main application instance (e.g., MultiScopeApp)
                          to access shared state like config, accounts, logs etc.
        """
        self.app = app_instance 
        self.biome_data = load_biome_data() 

        self.log_arrays = []
        self.username_log_map = {}
        self.last_log_update = 0
        self.last_log_array_update_time = 0 
        self.account_biomes = {} 
        self.accounts = [acc.get("username") for acc in self.app.accounts if acc.get("username")]
        self.last_webhook_time = 0
        self.webhook_rate_limit = DEFAULT_WEBHOOK_RATE_LIMIT
        self.account_last_sent_webhook = {} 
        self.sent_webhooks_cache = set() 
        self.first_detection_skipped = {} 

        # Merchant detection attributes
        self.merchant_webhook_url = self.app.config.get("merchant_webhook_url", "")
        self.merchant_notification_enabled = self.app.config.get("merchant_notification_enabled", True)
        self.merchant_jester_enabled = self.app.config.get("merchant_jester_enabled", True)
        self.merchant_mari_enabled = self.app.config.get("merchant_mari_enabled", True)
        self.merchant_jester_ping_config = self.app.config.get("merchant_jester_ping_config", {"id": "", "type": "None"})
        self.merchant_mari_ping_config = self.app.config.get("merchant_mari_ping_config", {"id": "", "type": "None"})
        self.account_last_merchant_log_line = {} # Stores the full log line of the last notified event
        self.last_merchant_webhook_time = 0 # For rate limiting merchant webhooks specifically
        self.account_merchant_cooldown = {} # Per-account cooldown to prevent duplicate notifications (30s)

        self.first_merchant_scan_completed_for_user = set() # Tracks users for whom initial merchant scan is done

        self._initialize_account_states()

    def reset_detection_states(self):
        """Resets the detection states, typically called when accounts change."""
        self.account_biomes = {} 
        self.accounts = [acc.get("username") for acc in self.app.accounts if acc.get("username")] 
        self.first_detection_skipped = {} 

        # Reset merchant related states
        self.merchant_webhook_url = self.app.config.get("merchant_webhook_url", "")
        self.merchant_notification_enabled = self.app.config.get("merchant_notification_enabled", True)
        self.merchant_jester_enabled = self.app.config.get("merchant_jester_enabled", True)
        self.merchant_mari_enabled = self.app.config.get("merchant_mari_enabled", True)
        self.merchant_jester_ping_config = self.app.config.get("merchant_jester_ping_config", {"id": "", "type": "None"})
        self.merchant_mari_ping_config = self.app.config.get("merchant_mari_ping_config", {"id": "", "type": "None"})
        self.account_last_merchant_log_line = {} # Reset this

        self.first_merchant_scan_completed_for_user = set() # Reset this as well

        self._initialize_account_states()

    def _initialize_account_states(self):
        """Initialize detection state for accounts present in the app config."""
        if not hasattr(self.app, 'accounts'):
            self.app.append_log("Debug: App instance has no 'accounts' attribute during init.")
            return
        self.app.append_log(f"Debug: Initializing states for accounts: {self.accounts}")
        for username in self.accounts:
            if username not in self.account_biomes:
                self.account_biomes[username] = None
            # Initialize merchant log line state for each account
            if username not in self.account_last_merchant_log_line:
                self.account_last_merchant_log_line[username] = {}
            if username not in self.account_merchant_cooldown:
                self.account_merchant_cooldown[username] = 0
        self.update_log_array()

    def update_log_array(self):
        """Updates self.log_arrays to have new log files in an array, newest first."""
        try:
            self.app.append_log(f"Debug: Updating log array from {ROBLOX_LOGS_DIR}")
            now = datetime.now().timestamp()

            timeThreshold = 7200
            files = [
                f for f in os.listdir(ROBLOX_LOGS_DIR)
                if os.path.isfile(os.path.join(ROBLOX_LOGS_DIR, f)) and
                now - os.path.getmtime(os.path.join(ROBLOX_LOGS_DIR, f)) <= timeThreshold
            ]
            files_sorted = sorted(files, key=lambda f: os.path.getmtime(os.path.join(ROBLOX_LOGS_DIR, f)), reverse=True)
            self.log_arrays = [os.path.join(ROBLOX_LOGS_DIR, f) for f in files_sorted]
            self.app.append_log(f"Debug: Found {len(self.log_arrays)} log files: {self.log_arrays[:5]}...") 

            # Rebuild the username_log_map
            new_username_map = {}
            self.app.append_log(f"Debug: Rebuilding username to log path map for {len(self.log_arrays)} logs.")
            for log_file_path in self.log_arrays: # log_arrays is sorted newest first
                retrieved_username = self.get_username(log_file_path) # Reads LOG_READ_SIZE
                if retrieved_username:
                    lower_username = retrieved_username.lower()
                    if lower_username not in new_username_map: # Keep the newest log for a user
                        new_username_map[lower_username] = log_file_path
            self.username_log_map = new_username_map
            self.app.append_log(f"Debug: Username map rebuilt. Size: {len(self.username_log_map)}. First 5 keys: {list(self.username_log_map.keys())[:5]}")

        except Exception as e:
            error_logging(e, "Error in update_log_array or username_map build")
            self.app.append_log(f"Error: Failed to update log array/map: {e}")

    def check_all_accounts_biomes(self):
        """Main loop function to check biomes for all configured accounts using multithreading."""
        try:
            now = time.time()
            if now - self.last_log_array_update_time > LOG_ARRAY_UPDATE_INTERVAL:
                self.app.append_log("Debug: Log array update interval reached, refreshing...")
                self.update_log_array()
                self.last_log_array_update_time = now

            # Use all configured accounts (self.accounts) instead of just active ones
            if not self.accounts: # Check if there are any configured accounts
                self.app.append_log("Debug: No configured accounts to check.")
                return

            # Set max_workers based on the total number of accounts configured in the app
            total_configured_accounts = len(self.app.accounts) # This is used for max_workers
            max_workers = total_configured_accounts if total_configured_accounts > 0 else 1
            
            self.app.append_log(f"Debug: Checking biomes for {len(self.accounts)} configured accounts. Max workers: {max_workers}")

            # Process all configured accounts concurrently
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_username = {
                    executor.submit(self.check_single_account_log, username): username
                    for username in self.accounts # Iterate over all configured accounts
                }

                completed_count = 0
                for future in concurrent.futures.as_completed(future_to_username):
                    username = future_to_username[future]
                    try:
                        future.result()
                    except Exception as e:
                        error_logging(e, f"Error in thread processing log for {username}")

        except Exception as e:
            error_logging(e, "Error in check_all_accounts_biomes")

    def get_last_rpc_msg(self, log_path):
        """Gets the latest RPC Message from the specific log path."""
        path_content = ""
        self.app.append_log(f"Debug: Entering get_last_rpc_msg for {log_path}") 
        if os.path.exists(log_path):
            try:
                self.app.append_log(f"Debug: Reading file content for RPC from {log_path}")
                with open(log_path,"r", encoding='utf-8', errors='ignore') as file:
                    # Read the whole file for simplicity now, can optimize later if needed
                    path_content = file.read()
                self.app.append_log(f"Debug: Read {len(path_content)} bytes for RPC from {log_path}")
                return self.get_rpc_from_content(path_content, log_path) # Call new refactored method
            except Exception as e:
                error_logging(e, f"Error reading file for RPC from {log_path}")
                self.app.append_log(f"Error: Exception in get_last_rpc_msg for {log_path}: {e}")
                return None
        else:
            self.app.append_log(f"Debug: Path does not exist in get_last_rpc_msg: {log_path}")
            return None

    def get_rpc_from_content(self, log_content, log_path_for_debug=""): # New method
        """Gets the latest RPC Message from the given log content."""
        self.app.append_log(f"Debug: Entering get_rpc_from_content for log: {log_path_for_debug}")
        if not log_content:
            self.app.append_log(f"Debug: Empty log content provided to get_rpc_from_content for {log_path_for_debug}")
            return None
        try:
            rpc_start_index = log_content.rfind("[BloxstrapRPC]")
            if rpc_start_index == -1:
                self.app.append_log(f"Debug: [BloxstrapRPC] marker not found in content from {log_path_for_debug}")
                return None

            rpc = log_content[rpc_start_index:]
            end_marker_index = rpc.find("}}}")
            if end_marker_index == -1:
                self.app.append_log(f"Debug: RPC end marker '}}}}' not found in content from {log_path_for_debug}")
                return None

            rpc = rpc[:end_marker_index+3]
            self.app.append_log(f"Debug: Successfully extracted RPC msg (length {len(rpc)}) from content of {log_path_for_debug}")
            return rpc
        except Exception as e:
            error_logging(e, f"Error processing RPC from content of {log_path_for_debug}")
            self.app.append_log(f"Error: Exception in get_rpc_from_content for {log_path_for_debug}: {e}")
            return None

    def get_username(self, log_path):
        path_content = ""
        self.app.append_log(f"Debug: Attempting to get username from {log_path}") 
        if os.path.exists(log_path):
            try:
                with open(log_path,"r", encoding='utf-8', errors='ignore') as file:
                    path_content = file.read(LOG_READ_SIZE)
                # Updated pattern to use PlayerGui reference for more reliable username extraction
                username_match = re.search(r"Players\.([^.]+)\.PlayerGui", path_content)
                if username_match:
                    username = username_match.group(1)
                    self.app.append_log(f"Debug: Extracted username '{username}' from {log_path}") 
                    return username
                else:
                    self.app.append_log(f"Debug: Username pattern not found in {log_path}") 
                    return None
            except Exception as e:
                error_logging(e, f"Error reading or extracting username from {log_path}")
                self.app.append_log(f"Error: Failed get_username for {log_path}: {e}")
                return None
        self.app.append_log(f"Debug: Log path does not exist (get_username): {log_path}") 
        return None

    def get_log_from_user(self,user):
        self.app.append_log(f"Debug: Searching for log file for user: {user} using pre-built map.")
        log_path = self.username_log_map.get(user.lower())
        if log_path:
            self.app.append_log(f"Debug: Found log file '{log_path}' for user '{user}' from map.")
        else:
            map_size = len(self.username_log_map)
            first_few_keys = list(self.username_log_map.keys())[:min(5, map_size)] # Defensive slicing
            self.app.append_log(f"Debug: Log file for user '{user}' not found in map (map size: {map_size}, first keys: {first_few_keys}).")
        return log_path

    def check_single_account_log(self, username):
        """Checks a single log file (tail only) for biome and merchant updates for a specific account."""
        self.app.append_log(f"Debug: Checking log for account: {username}")
        try:
            log_path = self.get_log_from_user(username)
            if log_path is None:
                self.app.append_log(f"Debug: No log path found for {username} via map, skipping.")
                return
            self.app.append_log(f"Debug: Using log path {log_path} for {username}")

            # Read log content - TAIL ONLY
            log_content = None
            if os.path.exists(log_path):
                try:
                    file_size = os.path.getsize(log_path)
                    # Determine the actual amount to read, ensuring it's not more than the file size
                    read_amount = min(file_size, LOG_TAIL_READ_BYTES) 
                    
                    with open(log_path, "r", encoding='utf-8', errors='ignore') as file:
                        if file_size > LOG_TAIL_READ_BYTES:
                            # Seek from the end of the file backwards by LOG_TAIL_READ_BYTES
                            # file.seek(0, os.SEEK_END) # Go to end
                            # file.seek(file.tell() - LOG_TAIL_READ_BYTES) # Go back by LOG_TAIL_READ_BYTES
                            # A simpler way for positive offsets from start:
                            file.seek(file_size - LOG_TAIL_READ_BYTES)
                        log_content = file.read(LOG_TAIL_READ_BYTES) # Read up to LOG_TAIL_READ_BYTES
                    self.app.append_log(f"Debug: Read last {len(log_content)} bytes (target: {LOG_TAIL_READ_BYTES}) from {log_path} for {username}")
                except FileNotFoundError:
                    self.app.append_log(f"Warning: FileNotFoundError for {log_path} (race condition after os.path.exists?). Skipping {username}.")
                    return # Skip if file disappeared
                except Exception as e:
                    error_logging(e, f"Error reading log file tail {log_path} for {username}")
                    self.app.append_log(f"Error: Could not read log tail {log_path} for {username}: {e}")
                    return
            else:
                self.app.append_log(f"Debug: Log path {log_path} does not exist (check_single_account_log). Should have been caught by get_log_from_user map logic if map is fresh.")
                return

            if not log_content:
                self.app.append_log(f"Debug: Empty log content for {username} from {log_path}, skipping.")
                return

            # Process for Biomes (RPC)
            rpc_message = self.get_rpc_from_content(log_content, log_path)
            if rpc_message:
                biome = self.get_biome_from_rpc(rpc_message)
                if biome:
                    self.app.append_log(f"Debug: Extracted biome '{biome}' for {username}")
                    self.handle_account_biome_detection(username, biome)
                else:
                    self.app.append_log(f"Debug: Could not extract biome from RPC for {username} in {log_path}")
            else:
                self.app.append_log(f"Debug: No RPC message found in {log_path} for {username}, skipping biome check.")

            # Process for Merchants
            self.process_merchant_events(username, log_content, log_path)

        except Exception as e:
            error_logging(e, f"Error in check_single_account_log for {username}")
            self.app.append_log(f"Error: check_single_account_log failed for {username}: {e}")

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

        if username not in self.first_detection_skipped:
            self.first_detection_skipped[username] = True
            self.app.append_log(f"⏭️ Skipping first biome notification for {username} to prevent false positives")
            return

        message_type = self.app.config.get("biome_notifier", {}).get(biome, "Message")
        notification_enabled = self.app.config.get("biome_notification_enabled", {}).get(biome, True)

        # Check biome data for force_notify, never_notify, and ping_everyone flags
        biome_info = self.biome_data.get(biome, {})
        if biome_info.get("force_notify", False):
            notification_enabled = True
            if biome_info.get("ping_everyone", False):
                message_type = "Ping"
        elif biome_info.get("never_notify", False):
            notification_enabled = False

        webhook_tasks = []

        if previous_biome and previous_biome in self.biome_data:
            prev_message_type = self.app.config.get("biome_notifier", {}).get(previous_biome, "Message")
            prev_notification_enabled = self.app.config.get("biome_notification_enabled", {}).get(previous_biome, True)
            prev_biome_info = self.biome_data.get(previous_biome, {})
            if prev_biome_info.get("force_notify", False):
                prev_message_type = "Message"
                prev_notification_enabled = True
            elif prev_biome_info.get("never_notify", False):
                prev_notification_enabled = False

            if prev_message_type != "None" and prev_notification_enabled:
                webhook_tasks.append(("end", previous_biome, prev_message_type))

        if message_type != "None" and notification_enabled:
            webhook_tasks.append(("start", biome, message_type))

        for event_type, biome_name, msg_type in webhook_tasks:
             self.send_account_webhook(username, biome_name, msg_type, event_type)

    def get_biome_from_rpc(self, rpc_message):
        """Extract biome name (largeImage hoverText) from Bloxstrap RPC msg using JSON parsing."""
        self.app.append_log(f"Debug: Entering get_biome_from_rpc")
        try:
            if not isinstance(rpc_message, str) or not rpc_message:
                self.app.append_log(f"Debug: get_biome_from_rpc received invalid input (type: {type(rpc_message)}, empty: {not rpc_message})")
                return None

            json_start_index = rpc_message.find('{')
            if json_start_index == -1:
                self.app.append_log("Debug: RPC message does not contain JSON start '{'")
                return None

            json_data_str = rpc_message[json_start_index:]

            rpc_data = json.loads(json_data_str)
            self.app.append_log("Debug: Successfully parsed RPC JSON.")

            large_image_data = rpc_data.get('data', {}).get('largeImage')
            if not large_image_data or not isinstance(large_image_data, dict):
                self.app.append_log("Debug: 'largeImage' data not found or not a dictionary in RPC.")

                return None

            found_biome = large_image_data.get('hoverText')
            if not found_biome or not isinstance(found_biome, str):
                self.app.append_log("Debug: 'hoverText' not found or not a string within largeImage.")

                return None

            self.app.append_log(f"Debug: Successfully extracted biome hoverText: {found_biome}")
            return found_biome

        except json.JSONDecodeError as json_e:
            error_logging(json_e, "Error decoding JSON from RPC message")
            self.app.append_log(f"Error: Failed to decode JSON in get_biome_from_rpc: {json_e}. RPC (start): {rpc_message[:200]}...")
            return None
        except Exception as e:
            error_logging(e, "Error parsing biome from RPC")
            self.app.append_log(f"Error: Unexpected exception in get_biome_from_rpc: {e}. RPC (start): {rpc_message[:200]}...")
            return None

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
            self.app.gui_manager.show_message_box("Error", "Webhook URL is empty.", "error")
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
            self.app.gui_manager.show_message_box("Success", "Test message sent successfully!", "info")
            self.app.append_log(f"Test webhook successful for URL ending in ...{webhook_url[-10:]}")
            return True
        except requests.exceptions.RequestException as e:
            error_msg = f"Webhook test failed: {e}"

            if response is not None:
                 if response.status_code == 404: error_msg += "\n(Webhook URL not found)"
                 elif response.status_code == 401: error_msg += "\n(Unauthorized - Invalid URL?)"
                 elif response.status_code == 400: error_msg += "\n(Bad request - Embed format issue?)"
            self.app.gui_manager.show_message_box("Error", error_msg, "error")
            error_logging(e, f"Failed to send test webhook to ...{webhook_url[-10:]}")
            return False
        except Exception as e:
             error_logging(e, f"Unexpected error testing webhook ...{webhook_url[-10:]}")
             self.app.gui_manager.show_message_box("Error", f"An unexpected error occurred: {e}", "error")
             return False

    def process_merchant_events(self, username, log_content, log_path_for_debug):
        """Processes log content for merchant events (Jester, Mari)."""
        if not self.merchant_notification_enabled: # Master switch for notifications
            return

        self.app.append_log(f"Debug: Processing merchant events for {username} from {log_path_for_debug}")
        
        merchant_pattern = re.compile(
            r"^(?P<full_line>" 
            r"(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z)," 
            r".*?" 
            r"\[Merchant\]: (?P<merchant_name>Jester|Mari) has arrived on the island" 
            r".*)$" 
            , re.MULTILINE 
        )

        found_merchants_in_current_scan = []
        for match in merchant_pattern.finditer(log_content):
            try:
                full_log_line = match.group("full_line").strip() 
                timestamp_str = match.group("timestamp")
                merchant_name = match.group("merchant_name")
                event_time_utc = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                
                found_merchants_in_current_scan.append({
                    "name": merchant_name, 
                    "time": event_time_utc, 
                    "log_path": log_path_for_debug,
                    "log_line": full_log_line 
                })
            except Exception as e:
                error_logging(e, f"Error parsing merchant event for {username} from {log_path_for_debug}")
                self.app.append_log(f"Error: Could not parse merchant line for {username}: {match.group(0)[:100]}... Error: {e}")

        if not found_merchants_in_current_scan:
            return

        found_merchants_in_current_scan.sort(key=lambda x: x["time"])

        # Ensure the per-user, per-merchant structure exists (it should from _initialize_account_states)
        if username not in self.account_last_merchant_log_line:
            self.account_last_merchant_log_line[username] = {}

        # === INITIAL SCAN LOGIC ===
        if username not in self.first_merchant_scan_completed_for_user:
            self.app.append_log(f"Debug: Performing initial merchant scan for {username} from {log_path_for_debug}. Notifications suppressed for these.")
            
            merchants_registered_in_initial_scan = set()
            for merchant_event in found_merchants_in_current_scan: 
                merchant_name = merchant_event["name"]
                log_line = merchant_event["log_line"]
                self.account_last_merchant_log_line[username][merchant_name] = log_line
                merchants_registered_in_initial_scan.add(merchant_name)
            
            for merchant_name in merchants_registered_in_initial_scan:
                 log_line_for_log = self.account_last_merchant_log_line[username].get(merchant_name, "")
                 self.app.append_log(f"⏭️ Initial Scan: Registered latest {merchant_name} for {username}. Log line: ...{log_line_for_log[-50:]}. No notification sent.")

            self.first_merchant_scan_completed_for_user.add(username)
            self.app.append_log(f"Debug: Initial merchant scan completed for {username}. Future new merchants will trigger notifications.")
            return # Crucial: Do not proceed to handle_merchant_detection for these initial finds
        # === END INITIAL SCAN LOGIC ===

        # === NORMAL PROCESSING (AFTER INITIAL SCAN) ===
        # From the current scan's findings, identify the latest event for each merchant type.
        latest_events_in_this_scan_by_type = {}
        for merchant_event in found_merchants_in_current_scan: # Already sorted by time
            # The last one encountered for each name will be the latest due to sorting.
            latest_events_in_this_scan_by_type[merchant_event["name"]] = merchant_event

        # Now, process only these latest events.
        for merchant_name, latest_event_data in latest_events_in_this_scan_by_type.items():
            self.handle_merchant_detection(
                username, 
                latest_event_data["name"], 
                latest_event_data["time"], 
                latest_event_data["log_line"], 
                latest_event_data["log_path"] 
            )

    def handle_merchant_detection(self, username, merchant_name, event_time_utc, log_line_content, log_path_for_debug):
        """Handles logic when a merchant is detected, using log line comparison for uniqueness."""
        if not self.merchant_notification_enabled:
            return
        
        # Individual merchant type switch
        if merchant_name == "Jester" and not self.merchant_jester_enabled:
            self.app.append_log(f"Debug: Jester detected for {username} but Jester notifications are disabled. Skipping.")
            return
        if merchant_name == "Mari" and not self.merchant_mari_enabled:
            self.app.append_log(f"Debug: Mari detected for {username} but Mari notifications are disabled. Skipping.")
            return

        if username not in self.account_last_merchant_log_line:
            self.account_last_merchant_log_line[username] = {}
        
        last_notified_log_line = self.account_last_merchant_log_line[username].get(merchant_name)

        # If we've never notified for this merchant for this user, or this log line is different from the last one
        if last_notified_log_line is None or log_line_content != last_notified_log_line:
            self.app.append_log(f"🎉 Merchant {merchant_name} detected for {username} (New log line). Sending notification. Line: ...{log_line_content[-50:]}")
            self.send_merchant_webhook(username, merchant_name, event_time_utc)
            self.account_last_merchant_log_line[username][merchant_name] = log_line_content
            # No self.app.config_changed = True here, as last_merchant_log_line is in-memory for the session
        else:
            self.app.append_log(f"Debug: Merchant {merchant_name} for {username} (Line: ...{log_line_content[-50:]}) is a duplicate of the last notified log line. Skipping.")

    def send_merchant_webhook(self, username, merchant_name, event_time_utc):
        """Sends a Discord webhook for a detected merchant."""
        if not self.merchant_webhook_url:
            self.app.append_log("Warning: Merchant webhook URL is not configured. Cannot send notification.")
            return

        # Basic rate limiting for merchant webhooks (separate from biome webhooks)
        current_time = time.time()
        time_since_last = current_time - self.last_merchant_webhook_time
        # Using the same rate limit variable for now, can be separated if needed
        if time_since_last < self.webhook_rate_limit: 
            sleep_time = self.webhook_rate_limit - time_since_last
            self.app.append_log(f"⏳ Rate limiting merchant webhook ({username}/{merchant_name}), waiting {sleep_time:.2f}s")
            time.sleep(sleep_time)
        self.last_merchant_webhook_time = time.time()

        original_username = username
        for account in self.app.accounts:
            if account.get("username", "").lower() == username.lower():
                original_username = account.get("username")
                break
        
        ps_link = self.app.get_ps_link_for_user(username)

        # Convert UTC event time to a Discord timestamp
        unix_timestamp = int(event_time_utc.timestamp())
        timestamp_full = f"<t:{unix_timestamp}:F>"
        timestamp_relative = f"<t:{unix_timestamp}:R>"

        merchant_emojis = {"Jester": "🃏", "Mari": "🛍️"}
        merchant_colors = {"Jester": 0xa352ff, "Mari": 0xff82ab} # Jester purple, Mari pink
        merchant_thumbnails = {
            "Jester": "https://raw.githubusercontent.com/cresqnt-sys/MultiScope/main/assets/jester_icon.png", # Placeholder
            "Mari": "https://raw.githubusercontent.com/cresqnt-sys/MultiScope/main/assets/mari_icon.png" # Placeholder
        }


        emoji = merchant_emojis.get(merchant_name, "📢")
        color = merchant_colors.get(merchant_name, 0x7289DA) # Default to Discord blurple
        thumbnail_url = merchant_thumbnails.get(merchant_name, "https://i.postimg.cc/mDzwFfX1/GLITCHED.png")


        title = f"{emoji} {merchant_name} Has Arrived!"
        description = f"**Account:** `{original_username}`\n"
        description += f"**Detected At:** {timestamp_full} ({timestamp_relative})\n"
        if ps_link:
            description += f"**Private Server:** {ps_link}\n"
        
        embed = {
            "title": title,
            "description": description,
            "color": color,
            "thumbnail": {"url": thumbnail_url},
            "footer": {
                "text": f"MultiScope | v{self.app.version}",
                "icon_url": "https://i.postimg.cc/mDzwFfX1/GLITCHED.png" # App icon
            },
            "timestamp": event_time_utc.isoformat() # ISO timestamp for the embed itself
        }
        
        payload = {"embeds": [embed]}

        ping_config = None
        if merchant_name == "Jester":
            ping_config = self.merchant_jester_ping_config
        elif merchant_name == "Mari":
            ping_config = self.merchant_mari_ping_config

        ping_content = ""
        if ping_config:
            ping_id = ping_config.get("id", "").strip()
            ping_type = ping_config.get("type", "None")

            if ping_id:
                if ping_type == "User ID":
                    ping_content = f"<@{ping_id}>"
                elif ping_type == "Role ID":
                    ping_content = f"<@&{ping_id}>"
                elif ping_id.startswith("@") or ping_id.startswith("<@"): # User entered @everyone, @here, or full <@ID> or <@&ID>
                    ping_content = ping_id
                elif ping_type == "None": # If type is None, but ID is provided, assume it's a custom string like @everyone or just text
                     ping_content = ping_id # Use the ID as is if type is None but ID is present
        
        payload["content"] = ping_content

        # Per-account cooldown check (30 seconds) to prevent duplicate notifications
        if username in self.account_merchant_cooldown:
            if self.account_merchant_cooldown[username] + 30 > current_time:
                self.app.append_log(f"Debug: Merchant notification for {username} skipped due to cooldown.")
                return
        self.account_merchant_cooldown[username] = current_time

        try:
            response = requests.post(
                self.merchant_webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            response.raise_for_status()
            self.app.append_log(f"✅ Merchant webhook sent for {original_username}/{merchant_name} to URL ending in ...{self.merchant_webhook_url[-10:]}")

            # Adjust rate limit similar to biome webhooks
            if self.webhook_rate_limit > DEFAULT_WEBHOOK_RATE_LIMIT:
                 self.webhook_rate_limit = max(DEFAULT_WEBHOOK_RATE_LIMIT, self.webhook_rate_limit - 0.1)

        except requests.exceptions.RequestException as e:
            error_logging(e, f"Failed to send merchant webhook for {original_username} to URL ending in ...{self.merchant_webhook_url[-10:]}")
            if response is not None and response.status_code == 429: # Check if response exists before accessing status_code
                self.webhook_rate_limit = min(self.webhook_rate_limit + 0.5, 5.0) # Use existing rate limit var
                self.app.append_log(f"Discord rate limit hit for merchant. Increased delay to {self.webhook_rate_limit:.1f}s")
                time.sleep(1.5)
        except Exception as e:
            error_logging(e, f"Unexpected error sending merchant webhook for {original_username} to ...{self.merchant_webhook_url[-10:]}")
