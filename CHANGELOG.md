# Changelog

All notable changes to BiomeScope will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.4-Beta2] - 2025-04-15

### Added
- Complete reimplementation of log handling system
- Auto-detection of accounts when not previously configured
- New and improved player detection mechanics

### Fixed
- Solved critical issue with NULL biome detections for inactive accounts
- Fixed log file validation to properly handle "Player added:" messages
- Enhanced username extraction from log files with the "load failed in Players" pattern

### Changed
- Rewrote account scanning for more reliable detection
- More intelligent log file filtering focusing on player logs with "last" in filename
- Reduced log spam by only reporting changes and new detections
- Completely overhauled the log file processing system for better reliability

## [1.0.4-Beta] - 2025-04-10

### Added
- Periodic account checking system that works even if Roblox is started after BiomeScope
- Enhanced log file validation to prevent false detections
- Improved timestamp checking for more accurate log processing
- Better handling for Roblox log file format
- Improved "load failed in Players" detection for more reliable username extraction

### Fixed
- Fixed issue where old logs could be incorrectly identified as current
- Stricter log association to prevent "NULL" biome detections for inactive accounts
- More robust "Player added:" message detection
- Removed loose pattern matching that could cause false positives
- Fixed inconsistent account detection when Roblox is started after BiomeScope

### Changed
- Increased scanning frequency for more responsive detection
- Better caching of log files with improved validation
- More detailed logging to track account and biome state changes
- Prioritizes "last" log files for more consistent detection

### Technical
- Rewritten log file sorting and filtering
- Improved username extraction from log files

## [1.0.3-Stable] - 2025-04-06

### Added
- Automatic Feature Flag Configuration
  - Automatically sets up required feature flags for all Roblox installations
  - No manual configuration needed
  - Works for Bloxstrap and Fishstrap installations
  - Improved logging for feature flag setup
  - First-time setup instructions for users
  - Ensures optimal logging and detection capabilities
- Configuration files now stored in AppData folder
  - Settings persist through application updates
  - Automatic migration of existing configs to AppData
- Improved logging with structured JSON format
- All testing updates added
- Updated to stable release
- Fixed other minor bugs

## [1.0.3-Testing2] - 2025-04-06

### Added
- Sub-second Biome detection for multiple accounts
- Auto updater system complete rewrite
- Minor bug fixes and performance improvements

## [1.0.3-Testing] - 2025-04-06

### Added
- Configurable biome notifications with customizable settings
- Sequential mode for Anti-AFK system
- Improved account detection with enhanced reliability
- Fixed most if all past reported bugs
- Rewritten webhook checking and sending
- Improved resource usage
- Improved Auto Updater on Testing versions

### Changed
- Complete Anti-AFK system rewrite for better performance and stability

## [1.0.2-Beta] - 2025-04-02

### Added
- Private Server link in Discord webhook embeds
- Start/Stop session times in webhook
- Account-specific biome notification selection for each webhook (selection)
- Improved biome detection system with faster response times
  - Sub 1-second detection times for both single and multiple accounts (Tested on 5 accounts running at the same time)
  - More efficient scanning algorithm

## [1.0.1-Hotfix] - 2025-04-01

### Fixed
- Added @everyone ping for Glitch and Dreamscape biome notifications

## [1.0.1-Beta] - 2025-04-01

### Fixed
- Anti-AFK system now properly detects user inactivity
- True-AFK mode correctly performs actions when user is inactive
- Improved action scheduling based on activity state
- Fixed overdue actions not being performed when user is inactive
- Reduced log spam for repeated status messages
- Added exe icons

## [1.0.0-Beta] - 2025-03-31

### Added
- Multi-account support: Track biomes across multiple Roblox accounts simultaneously
- Multi-webhook support: Send notifications to multiple Discord webhooks
- AntiAFK system with multiple action types (space, ws, zoom)
- True-AFK mode that only performs actions when user is inactive
- Automatic update checker and downloader
- Session timer and statistics tracking
- Improved UI with ttkbootstrap theming
- Basic biome detection for Sols RNG
- Single account monitoring
- Discord webhook notifications
- Simple statistics tracking
- Activity logging
- Basic UI

### Changed
- Better error handling throughout the application
- More detailed activity logging
- Rate limiting for webhook notifications

### Fixed
- Various webhook formatting issues
- Session time tracking bugs
- UI responsiveness in high DPI displays

[Unreleased]: https://github.com/cresqnt-sys/BiomeScope/compare/v1.0.4-Beta2...HEAD
[1.0.4-Beta2]: https://github.com/cresqnt-sys/BiomeScope/compare/v1.0.4-Beta...v1.0.4-Beta2
[1.0.4-Beta]: https://github.com/cresqnt-sys/BiomeScope/compare/v1.0.3-Stable...v1.0.4-Beta
[1.0.3-Stable]: https://github.com/cresqnt-sys/BiomeScope/compare/v1.0.3-Testing2...v1.0.3-Stable
[1.0.3-Testing2]: https://github.com/cresqnt-sys/BiomeScope/compare/v1.0.3-Testing...v1.0.3-Testing2
[1.0.3-Testing]: https://github.com/cresqnt-sys/BiomeScope/compare/v1.0.2-Beta...v1.0.3-Testing
[1.0.2-Beta]: https://github.com/cresqnt-sys/BiomeScope/compare/v1.0.1-Hotfix...v1.0.2-Beta
[1.0.1-Hotfix]: https://github.com/cresqnt-sys/BiomeScope/compare/v1.0.1-Beta...v1.0.1-Hotfix
[1.0.1-Beta]: https://github.com/cresqnt-sys/BiomeScope/compare/v1.0.0-Beta...v1.0.1-Beta
[1.0.0-Beta]: https://github.com/cresqnt-sys/BiomeScope/releases/tag/v1.0.0-Beta 