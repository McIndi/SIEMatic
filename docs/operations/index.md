---
title: Operations Guide
---

# Operations Guide

This guide covers the production-oriented Docker Compose deployment and the
day-to-day administration of SIEMatic.

SIEMatic has four application roles: web, indexer, agent, and crawler. The
provided Compose project runs one container for each role plus PostgreSQL. All
roles share the same application image but select role-specific Django settings
and management commands.

Before operating SIEMatic, read:

- [Deploying](deploying.md) for secrets, certificates, Compose, and air-gapped
  packages
- [User and Permission Management](user-and-permission-management.md) for the
  `Registered User` and `Agent` groups
- [Crawler Configuration](crawler-configuration.md), [Alerting](alerting.md),
  and [Data Retention](data-retention.md) for background analytics
- [Backup and Restore](backup-and-restore.md) and [Upgrading](upgrading.md)
  before changing a running installation
- [Troubleshooting](troubleshooting.md) for service and connectivity checks.

The settings are divided among `SIEMatic/settings/base.py`, `web.py`,
`indexer.py`, `agent.py`, and `crawler.py`. Environment variables are cataloged
in [Settings and Environment Variables](../reference/settings-and-env-vars.md).
