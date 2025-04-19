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
        self.last_log_update = 0
        self.last_log_array_update_time = 0 
        self.account_biomes = {} 
        self.accounts = [acc.get("username") for acc in self.app.accounts if acc.get("username")]
        self.last_webhook_time = 0
        self.webhook_rate_limit = DEFAULT_WEBHOOK_RATE_LIMIT
        self.account_last_sent_webhook = {} 
        self.sent_webhooks_cache = set() 
        self.first_detection_skipped = {} 

        self._initialize_account_states()

    def reset_detection_states(self):
        """Resets the detection states, typically called when accounts change."""
        self.account_biomes = {} 
        self.accounts = [acc.get("username") for acc in self.app.accounts if acc.get("username")] 
        self.first_detection_skipped = {} 

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
        except Exception as e:
            error_logging(e, "Error in update_log_array")
            self.app.append_log(f"Error: Failed to update log array: {e}")

    def check_all_accounts_biomes(self):
        """Main loop function to check biomes for *active* accounts."""
        try:

            now = time.time()
            if now - self.last_log_array_update_time > LOG_ARRAY_UPDATE_INTERVAL:
                self.app.append_log("Debug: Log array update interval reached, refreshing...")
                self.update_log_array()
                self.last_log_array_update_time = now

            active_usernames = self.app.active_accounts
            if not active_usernames:

                return

            max_workers = max(1, min(8, len(active_usernames)))
            self.app.append_log(f"Debug: Checking biomes for {len(active_usernames)} active accounts: {active_usernames}")

            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:

                future_to_username = {
                    executor.submit(self.check_single_account_log, username): username
                    for username in active_usernames 
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
                    path_content = file.read()
                self.app.append_log(f"Debug: Read {len(path_content)} bytes for RPC from {log_path}")

                rpc_start_index = path_content.rfind("[BloxstrapRPC]")
                if rpc_start_index == -1:
                    self.app.append_log(f"Debug: [BloxstrapRPC] marker not found in {log_path}")
                    return None

                rpc = path_content[rpc_start_index:]
                end_marker_index = rpc.find("}}}")
                if end_marker_index == -1:
                    self.app.append_log(f"Debug: RPC end marker '}}'}}' not found in {log_path}")

                    return None

                rpc = rpc[:end_marker_index+3]
                self.app.append_log(f"Debug: Successfully extracted RPC msg (length {len(rpc)}) from {log_path}")
                return rpc
            except Exception as e:
                error_logging(e, f"Error reading or processing RPC from {log_path}")
                self.app.append_log(f"Error: Exception in get_last_rpc_msg for {log_path}: {e}")
                return None
        else:
            self.app.append_log(f"Debug: Path does not exist in get_last_rpc_msg: {log_path}")
            return None

    def get_username(self, log_path):
        path_content = ""
        self.app.append_log(f"Debug: Attempting to get username from {log_path}") 
        if os.path.exists(log_path):
            try:
                with open(log_path,"r", encoding='utf-8', errors='ignore') as file:
                    path_content = file.read(LOG_READ_SIZE)
                username_match = re.search(r"load failed in Players\.([^.]+)\.", path_content)
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
        self.app.append_log(f"Debug: Searching for log file for user: {user}")
        for log_file_path in self.log_arrays:
            retrieved_username = self.get_username(log_file_path)
            if retrieved_username is not None and retrieved_username.lower() == user.lower():
                self.app.append_log(f"Debug: Found log file '{log_file_path}' for user '{user}'")
                return log_file_path
        self.app.append_log(f"Debug: Log file for user '{user}' not found in {len(self.log_arrays)} checked logs.")
        return None

    def check_single_account_log(self, username):
        """Checks a single log file for biome updates for a specific account."""
        self.app.append_log(f"Debug: Checking log for account: {username}")
        try:
            log_path = self.get_log_from_user(username)
            if log_path is None:
                self.app.append_log(f"Debug: No log path found for {username}, skipping.")
                return
            self.app.append_log(f"Debug: Using log path {log_path} for {username}")

            rpc_message = self.get_last_rpc_msg(log_path)
            if rpc_message is None:
                self.app.append_log(f"Debug: No RPC message found in {log_path} for {username}, skipping.")
                return

            biome = self.get_biome_from_rpc(rpc_message)
            if biome:
                self.app.append_log(f"Debug: Extracted biome '{biome}' for {username}")
                self.handle_account_biome_detection(username, biome)
            else:
                self.app.append_log(f"Debug: Could not extract biome from RPC for {username}")
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

        if biome in ["GLITCHED", "DREAMSPACE"]:
            message_type = "Ping" 
            notification_enabled = True 
        elif biome == "NORMAL":
            notification_enabled = False  

        webhook_tasks = []

        if previous_biome and previous_biome in self.biome_data:
            prev_message_type = self.app.config.get("biome_notifier", {}).get(previous_biome, "Message")
            prev_notification_enabled = self.app.config.get("biome_notification_enabled", {}).get(previous_biome, True)
            if previous_biome in ["GLITCHED", "DREAMSPACE"]: 
                prev_message_type = "Message" 
                prev_notification_enabled = True
            elif previous_biome == "NORMAL":
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