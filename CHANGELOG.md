# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.9.9.1-Stable] - 2025-11-29
### Added
- Added new CYBERSPACE biome with dedicated icon
- Added external `assets/biomes.json` configuration file for remote biome updating
- Added remote biome fetching from GitHub - biomes now auto-update on app restart without requiring a full app update
- Added `force_notify` field to biomes.json - biomes with this set to `true` cannot have notifications disabled
- Added `ping_everyone` field to biomes.json - biomes with this set to `true` will use @everyone ping
- Added `never_notify` field to biomes.json - biomes with this set to `true` will never send notifications (like NORMAL)

### Changed
- Detection logic now uses biome data fields for notification behavior instead of hardcoded checks
- Biome loading priority: Remote GitHub URL > Local assets/biomes.json > Hardcoded fallback defaults
- Updated [LICENSE](https://github.com/cresqnt-sys/MultiScope/blob/main/LICENSE), if you work on MultiScope currently you are highly encouraged to view changes.

### Removed
- Removed BLOOD RAIN, PUMPKIN MOON, GRAVEYARD, and BLAZING SUN biomes (no longer in game)
- Removed hardcoded special biome lists (`["GLITCHED", "DREAMSPACE", "BLAZING SUN"]`) - now configured via biomes.json

## [0.9.9-Stable] - 2025-11-26
### Added
- Updated app version to 0.9.9-Stable
- Added Merchants tab and merchant notification UI with per-merchant toggles (Jester/Mari) and webhook testing
- Added merchant detection for Jester and Mari with Discord webhook support
- Added per-account merchant notification cooldown to prevent duplicate merchant notifications (default 30s)
- Added merchant configuration defaults to `utils.py` (`merchant_webhook_url`, `merchant_notification_enabled`, `merchant_jester_enabled`, `merchant_mari_enabled`, `merchant_jester_ping_config`, `merchant_mari_ping_config`)

### Changed
- Updated version references in `main.py`, `app.py`, and `README.md` (bumped to 0.9.9)
- UI improvements: replaced fixed window geometry with dynamic minimum-size calculations and automatic centering; improved layout behavior and window sizing
- Improved username extraction from Roblox logs by using `Players.<username>.PlayerGui` pattern for more reliable detection
- Persisted merchant settings in application state (`app.py`) and exposed them in the GUI (`main.py`)—users can now configure merchant ping targets and toggle per-merchant notifications
- Updated Credits: added `ManasAarohi` and corrected `Maxstellar` spelling; updated copyright years

### Fixed
- Fixed duplicate merchant webhook notifications by implementing a per-account merchant cooldown and improving webhook rate-limiting
- Fixed various minor UI and session handling issues (session saving, hotkey error handling)

## [0.9.8-Stable] - 2025-10-18
### Added
- Added new biomes: BLOOD RAIN, PUMPKIN MOON, GRAVEYARD

### Changed
- Updated biome thumbnail URLs
- Updated app version to 0.9.8-Stable

## [0.9.7-Beta] - 2025-07-06
### Fixed
- Fixed BLAZING SUN biome detection issues for existing users by implementing automatic biome configuration migration
- Added automatic merging of new biomes into existing user `biomes_data.json` files
- Added automatic merging of new biomes into existing user `config.json` files for `biome_counts`, `biome_notification_enabled`, and `biome_notifier` sections
- Ensured BLAZING SUN biome is properly configured with correct notification settings (always notify with ping) for all users
- Made biome configuration future-proof to automatically handle new biomes in future updates without requiring manual user intervention

## [0.9.6-Beta] - 2025-07-05
### Added
- Added new "BLAZING SUN" biome detection with hover text "BLAZING SUN" and asset ID 107114559110957
- Implemented automatic Tcl/Tk library path detection to resolve GUI startup issues
- Added other minor bug fixes

### Changed
- "BLAZING SUN" biome is now configured as an "always on" biome (like GLITCHED and DREAMSPACE)
- Updated biome data loading to preserve emoji information from default configurations

### Fixed
- Resolved "Can't find a usable init.tcl" error that prevented application startup
- Fixed biome data loading to ensure all biomes appear in configuration interface

## [0.9.5-Beta] - 2025-05-13
### Added
- Added tooltip descriptions for various UI elements (test webhook button, Discord/GitHub links).
- Implemented dynamic adjustment of scrollable areas (webhook list, account checklist) based on content and window size.
- Added error handling for webhook testing (`show_message_box`).
- Added MULTI MERCHANT support

### Changed
- Refactored webhook account selection UI in `main.py` (`_add_webhook_entry`, `_populate_account_checklist`, `_toggle_account_selection`).
- Corrected `test_webhook` calls in `detection.py` to use `self.app.gui_manager.show_message_box`.
- Improved mousewheel scrolling behavior for nested scrollable frames.
- Ensured account lists in webhook settings refresh when accounts are managed.

### Fixed
- Resolved `AttributeError` when testing webhooks due to incorrect `show_message_box` calls.
- Addressed potential UI layout issues with nested scroll frames and dynamic content.
- Fixed bug where removing a webhook entry might cause index errors or incorrect numbering.
- Ensured mousewheel binding/unbinding is handled correctly for different tabs.

## [0.9.5-Alpha] - 2025-04-22
### Added
- Implemented checkmarks for account selection per webhook, replacing the previous listbox implementation.
- Added tooltip descriptions for various UI elements (test webhook button, Discord/GitHub links).
- Implemented dynamic adjustment of scrollable areas (webhook list, account checklist) based on content and window size.
- Added error handling and user feedback for webhook testing (`show_message_box`).

### Changed
- Refactored webhook account selection UI in `main.py` (`_add_webhook_entry`, `_populate_account_checklist`, `_toggle_account_selection`).
- Corrected `test_webhook` calls in `detection.py` to use `self.app.gui_manager.show_message_box`.
- Improved mousewheel scrolling behavior for nested scrollable frames.
- Ensured account lists in webhook settings refresh when accounts are managed.

### Fixed
- Resolved `AttributeError` when testing webhooks due to incorrect `show_message_box` calls.
- Addressed potential UI layout issues with nested scroll frames and dynamic content.
- Fixed bug where removing a webhook entry might cause index errors or incorrect numbering.
- Ensured mousewheel binding/unbinding is handled correctly for different tabs.

## [0.0.9-Alpha] - 2025-04-19

### Added
- Redid README.
- CHANGELOG.md file based on Keep a Changelog format.
- Added project logo and multiple badges (License, GitHub stats, Discord invite) to `README.md`.
- Implemented skipping the first biome detection per account to prevent initial false positives.
- Added periodic log file checking to detect new Roblox sessions dynamically.
- Added "Bored Man" to contributors list in `main.py`.

### Changed
- Updated `README.md` with detailed project information, credits, and contact links (Discord/GitHub).
- Improved logo display formatting and alignment in `README.md`.
- Refactored biome detection logic for simplicity, focusing on latest log files and RPC messages.
- Enhanced Credits tab UI with better padding, font adjustments, and grid layout.
- Improved status bar appearance with adjusted padding, relief, and font.
- Rebranded to MultiScope

### Fixed
- Corrected cutoff copyright label in the Credits tab.
- Increased default window height to prevent status bar cutoff.
- Resolved biome detection issues related to account iteration (`check_all_accounts_biomes`).
- Handled `UnicodeDecodeError` during log file reading by enforcing UTF-8 encoding and adding error handling.
- Fixed `AttributeError` in `DetectionManager` by adding the `reset_detection_states` method.
- Addressed linter errors (escaped quotes, indentation) in `detection.py` docstrings/comments.
- Fixed `AttributeError` in `antiafk.py`'s `toggle_antiafk` method by using a `config_changed` flag instead of a direct `save_config` call.