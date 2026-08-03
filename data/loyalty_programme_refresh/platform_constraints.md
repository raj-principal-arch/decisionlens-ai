# Platform Constraints — Care Club

> **Synthetic document.** Fictional systems and limits. No real Walmart data.
> Owner: engineering. Created: 2025-10-01. Last updated: 2025-11-20.

## EPOS estate

96 of the 436 stores are still on the Pellworth EPOS build and will not read the Care Club barcode. Members shopping in those stores cannot earn or redeem at the till. The migration is scheduled to complete in 2026-Q4.

## Points ledger

The rebuilt app reads balances from the legacy points ledger through a read-only feed refreshed every four hours. Real-time balance display and instant-award mechanics are not possible until the ledger is replaced. No replacement is scheduled.

## Experimentation

The rebuilt app has no feature-flag or A/B framework. Any experiment must be run as a manual store-level split, with allocation held in a spreadsheet by the analytics team.

## Push notifications

Member marketing notifications share a delivery channel with dispensing-ready alerts. Dispensing alerts take priority, and marketing sends are held in any store with a dispensing queue backlog.

## Member data warehouse

Member-level tables refresh weekly, on Sunday night. Daily or same-day measurement of a member-facing change is not currently possible.
