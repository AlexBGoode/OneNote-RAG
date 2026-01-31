# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial project structure with Microsoft OneNote authentication
- Docker and Docker Compose support for headless operation
- Environment-aware token storage (local vs Docker)
- Rate limit protection with configurable delays
- Comprehensive documentation and setup scripts

### Features
- Microsoft OAuth 2.0 device code flow authentication
- Automatic token refresh with persistent storage
- Multiple token storage strategies
- API rate limit protection
- Non-root Docker container for security

### Security
- Token files stored with 600 permissions
- Docker containers run as non-root user
- Environment variable based configuration
- Secrets management guidance

## [0.1.0] - 2026-01-31

### Initial Release
- Basic OneNote authentication with MSAL
- Token persistence to filesystem
- Docker support
- Basic API testing for notebooks retrieval
