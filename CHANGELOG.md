# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]


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