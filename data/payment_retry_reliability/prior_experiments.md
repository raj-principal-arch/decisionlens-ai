# Prior Experiments — Payment Reliability

> **Synthetic document.** Fictional experiments and fictional results. No real Walmart data.
> Owner: payments-product. Last updated: 2026-02-20.

## Retry timing test (August to September 2025)

The second retry for card failures was moved from 15 minutes after the first attempt to four hours after it. Eligible failures were randomised between arms.

Card retry recovery was 41.6% in the treatment arm against 39.1% in the control arm, over 24,800 eligible failures. The difference is statistically significant at p = 0.03.

The test covered card methods only. Bank mandate collections were excluded because they are not routed through the Retry Orchestrator.

The test ran before the 2026-Q1 denominator change. Its recovery metric is unaffected by that change because it is computed per eligible failure rather than per checkout session.

## Mandate failure sample review (February 2026)

A manual review of 60 failed mandate collections from a single week found: 22 recorded as mandate no longer valid at the buyer's bank, 19 as insufficient funds, 11 as account closed, and 8 unmapped.

All 60 came from one weekly batch and from buyers onboarded in the same quarter. Reason codes were read by hand from the scheme return file because they are not parsed by any system.

No follow-up review has been run and the finding has not been reproduced at scale.

## Not attempted

No test has been run on mandate re-validation at setup, on prompting a fallback payment method after a failure, or on any change to the orchestrator's lease behaviour.
