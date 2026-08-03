# Prior Search Experiments and Studies

> **Synthetic document.** Fictional experiments, fictional results. No real Walmart data.
> Owner: analytics-and-research. Last updated: 2026-07-06.

## Synonym mapping pilot — secondary storefront (10 November – 24 December 2025)

Catalogue operations hand-mapped 120 synonyms covering the highest-volume zero-result terms of 2025-Q3 and deployed them to the secondary storefront only. That storefront carries roughly 8% of group search volume, so the pilot does not move the group figures reported by analytics.

Zero-result rate for the 120 mapped terms fell from 100% to 3.2%. Storefront-wide zero-result rate fell by 0.9 percentage points. Search-to-cart conversion on that storefront moved from 11.8% in the four weeks before the pilot to 12.3% during it.

There was no holdout group. The pilot ran across the holiday trading peak, when search-to-cart conversion rises on both storefronts every year. The conversion movement cannot be separated from the season.

## Offline ranking evaluation (February 2026)

Engineering trained a learning-to-rank prototype on twelve months of click logs and evaluated it offline against the same logs. Reported NDCG@10 improved by 0.06 over the current ranker.

The training signal is what customers clicked in the ordering the current ranker gave them. Position bias has never been corrected for, so the evaluation rewards reproducing the existing ordering. The prototype has never been served to a customer.

## Trade terminology interviews (March 2026)

Nine trade customers were interviewed. Eight of the nine said they abandon the site when their term returns nothing and either telephone the trade counter or buy elsewhere.

Participants were recruited at the trade counters of two stores, so every one of them already shops with us in person.

## Zero-result categorisation (2 July 2026)

Catalogue operations reviewed the eighteen highest-volume zero-result query terms of 2026-Q2 by hand and assigned a cause to each.

Those eighteen terms account for 7.3% of zero-result search volume in the quarter. The remaining tail has never been categorised, and nothing is known about whether its causes resemble the head.

## Never attempted

No human-judged relevance set has ever been built. No online A/B test of ranking has been run.

Nothing in our reporting measures a search that returns results the customer then ignores. Every findability measure we publish is a measure of searches that returned nothing.
