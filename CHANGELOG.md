# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.9.6-Alpha] - 2025-07-05
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