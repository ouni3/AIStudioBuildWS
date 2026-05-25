# Changelog - AIStudioBuildWS

## [v1.0.1-p4] - 2026-05-25

### Added
- chore(settlement): initialize profit.md for EP-01 settlement ledger
- chore(settlement): add memory-bank/agents/ tracking for code agent

### Changed
- chore(settlement): auto commit updates for Phase 4

### Maintenance
- Initial Phase 4 settlement — lightweight-async-pre branch
- Docker Compose 3-shard cluster configuration (aistudio-shard-0/1/2)
- SHARD_INDEX and SHARD_COUNT environment injection per shard

---

## [v1.0.0] - 2026-05-25 (Initial)

### Added
- feat: implement lightweight async architecture with single browser process
- feat: WebSocket logging with web-based toggle switch
- feat: Cookie verification automation with camoufox

### Fixed
- fix(browser): mask URLs in navigation logs
- fix(logging): ensure logs dir exists before manager logger
- fix: reduce CPU load and log noise for browser instances
