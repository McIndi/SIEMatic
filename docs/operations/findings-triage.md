---
title: Findings Triage
---

# Findings Triage

Crawler plugins create findings linked to the event that triggered the rule.
Each finding records its rule, description, severity, optional MITRE tactic and
technique, status, assignee, notes, and timestamps.

## Review the queue

Open `/findings/`. The list can be filtered by severity, status, partial rule
name, and creation-date range. Open a finding to inspect its source event and
analytic context.

Use this workflow consistently:

1. Leave an unreviewed item as `New`.
2. When an analyst accepts responsibility for review, set it to `Acknowledged`.
3. Assign an active user, add investigation notes, and use `In progress` while
   work continues.
4. When remediation or investigation is complete, choose `Resolved`.
5. When the rule incorrectly created a finding, choose `False positive`.

The list supports bulk status changes. Assignment and notes are edited on the
detail page. Status changes do not delete the linked event or suppress future
findings. Each crawler's `realert_cooldown` controls suppression.

Users need `crawlers.view_finding` to inspect findings and
`crawlers.change_finding` to triage them. Deletion is restricted to staff users
and removes investigation history. Delete a finding only in exceptional cases.
