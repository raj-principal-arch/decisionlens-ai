# Search Platform — Constraints and Known Limits

> **Synthetic document.** Fictional systems, fictional limits. No real Walmart data.
> Owner: Nadia Fenwick, search platform engineering. Last updated: 2026-06-30.

## Current engine

Site search runs on an in-house term-frequency keyword index over 1.2 million SKUs. There is no vector index and no learned ranking stage. Ordering is keyword match score with a merchandising boost applied afterwards.

## Instrumentation change, 19 January 2026

Since 19 January 2026 the mobile app and the web category pages issue their queries through the search service, and those queries are recorded as search events. Category browse queries almost always return results.

Any rate expressed per search event is therefore not comparable across that date. Analytics publishes a restated series computed on typed-and-submitted queries only; that restated series is comparable across the change and the headline series is not.

## Re-platform

Building a vector index requires embedding all 1.2 million SKUs and operating a GPU serving tier, which we do not run today. Engineering has not estimated the work.

## Release calendar

The storefront code freeze runs from 2026-10-15 to 2027-01-05. No storefront code ships in that window.

Synonym dictionary updates are data rather than code. They deploy weekly through the catalogue pipeline and are exempt from the freeze.

## Catalogue data

Only 41% of SKUs have structured size or dimension attributes populated. Attribute-filtered search cannot be built on the current data.

## Performance

Search must return within 400 ms at p95. The current index averages 180 ms. A re-ranking stage would consume part of that headroom and nobody has measured how much.

## Logging

Click logs record the product clicked and the position it occupied in the result list. Position bias has never been corrected for in any analysis run against them.
