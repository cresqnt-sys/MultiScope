# Changelog

All notable changes to BiomeScope will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.0.2-Hotfix] - 2025-04-03

### Fixed
- Multi-account webhook issue where notifications weren't being sent for some accounts
- Improved detection of new Roblox instances started after the macro is running
- Enhanced log file detection to find and associate all account logs properly
- Made Roblox process detection more precise by exactly matching "RobloxPlayerBeta.exe" and using PID better
- Improved log file cache management when new instances are detected

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

[Unreleased]: https://github.com/cresqnt-sys/BiomeScope/compare/v1.0.2-Hotfix...HEAD
[1.0.2-Hotfix]: https://github.com/cresqnt-sys/BiomeScope/compare/v1.0.2-Beta...v1.0.2-Hotfix
[1.0.2-Beta]: https://github.com/cresqnt-sys/BiomeScope/compare/v1.0.1-Hotfix...v1.0.2-Beta
[1.0.1-Hotfix]: https://github.com/cresqnt-sys/BiomeScope/compare/v1.0.1-Beta...v1.0.1-Hotfix
[1.0.1-Beta]: https://github.com/cresqnt-sys/BiomeScope/compare/v1.0.0-Beta...v1.0.1-Beta
[1.0.0-Beta]: https://github.com/cresqnt-sys/BiomeScope/releases/tag/v1.0.0-Beta 