# Technical Constraints — Store Systems

> **Synthetic document.** Fictional systems and limits. No real Walmart data.
> Owner: engineering. Last updated: 2026-06-26.

## Till pricing

The till price file is regenerated once nightly at 02:00. Intra-day price changes are not possible on the current EPOS release.

The EPOS release that supports intra-day price updates enters pilot in Q1 2027. No date is committed for estate-wide rollout.

## Electronic shelf labels

Electronic shelf labels are fitted in 43 stores. The estate refresh programme reaches a further 77 stores by the end of Q1 2027 and carries the hardware cost centrally, so there is no incremental capital cost to the fresh programme for those stores.

Stores outside the refresh schedule have no funded route to shelf labels.

## Expiry data

There is no supplier or inventory feed of item-level remaining shelf life. Expiry dates exist only where a colleague has scanned the item at the fixture, and scanning is not enforced.

## Demand forecasting

Demand forecasts are produced at depot level. There is no store-level forecast, and the forecasting platform holds no shelf-life or expiry data.

## Store devices

Each store shares one handheld device between the colleagues on shift. There is no per-colleague device and none is planned in FY26.

## Measurement

Markdown and waste records reach the analytics warehouse on a T+2 schedule. Same-week measurement of any change is not possible.
