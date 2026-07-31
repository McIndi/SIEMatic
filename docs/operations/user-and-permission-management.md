---
title: User and Permission Management
---

# User and Permission Management

SIEMatic uses Django users, groups, and model permissions. Public
self-registration is disabled. Administrators provision every account.

For local development, `python manage.py rundev` creates the reserved
`siematic-admin` superuser automatically. Its random password is in
`rundev-superuser.txt` at the repository root and changes every time `rundev`
starts. This file and account are for local development only. Production
administrators must be provisioned separately as described in
[Deploying](deploying.md).

## Built-in groups

Migrations create and maintain two groups:

- `Registered User` grants view permissions for events, dashboards, panels,
  findings, and saved searches. A newly created user is added automatically.
- `Agent` grants `events.add_event`, which is required for event ingestion.

The groups serve different purposes. An agent service account normally belongs
to both because automatic user creation adds `Registered User`. Do not grant it
staff or superuser status.

## Provision an ordinary user

1. Sign in to `/admin/` as an administrator.
2. Open **Project > Custom users** and create the account.
3. Confirm that the account is active and belongs to `Registered User`.
4. If the person's job requires more access, add the necessary permissions or groups.

Users can manage their own saved searches. A saved search can remain private,
be shared with selected users, or be public to authenticated users. Ownership
still controls editing and deletion.

## Provision an ingest identity

1. Create a dedicated, non-staff user with a strong generated password.
2. Add it to `Agent` under **Authentication and Authorization > Groups**.
3. Put its credentials in the agent's secret store as `INDEXER_USERNAME` and
   `INDEXER_PASSWORD`.
4. Restart the agent. Make sure that ingestion does not return HTTP 403.

Never reuse a human administrator account for ingestion. Rotate an agent
password by updating Django and the agent secret together, then restarting the
agent.

## Finding permissions

Viewing findings requires `crawlers.view_finding`. Changing status, assignee,
or notes additionally requires `crawlers.change_finding`. Only staff users can
delete findings through the UI. Grant these capabilities explicitly to analyst
groups rather than broadening the default `Registered User` group.
