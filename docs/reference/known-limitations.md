---
title: Known Limitations
---

# Known Limitations

## Shared container health check

The image-level Dockerfile `HEALTHCHECK` probes port 8000 and is inherited by all four SIEMatic application services in `docker-compose.yaml`. Only `siematic-web` listens on that port, so the indexer, agent, and crawler containers can be reported as unhealthy even when they are operating normally. Treat those health states as unreliable until health checks are defined per service.

## Alert subscriptions are configuration-based

Alert recipients and thresholds are configured through crawler settings. SIEMatic does not yet provide a database-backed `AlertSubscription` model or a general database-backed configuration table, so users cannot manage personal rule or severity subscriptions through the application.
