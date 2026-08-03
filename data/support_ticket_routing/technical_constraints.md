# Technical Constraints — Support Platform

> **Synthetic document.** Fictional systems and limits. No real Walmart data.
> Owner: support-engineering. Created 2026-04-02. Last updated: 2026-06-25.

## Routing at ticket creation

The support platform requests a routing decision once, at ticket creation, and waits at most 400 ms for it. A router that does not answer inside that budget drops the ticket into the general queue, where it waits for manual pickup. Any replacement router must answer within the same budget.

The platform accepts one automated assignment per ticket. Every move after the first must be agent-initiated. A router cannot re-route a ticket it got wrong.

## Model serving

The internal model-serving platform, Modelyard, went live on 2026-02-09. It hosts CPU inference for models up to 2 GB and already carries two models for the fulfilment team. Adding a third model requires no new infrastructure and no new vendor. There is no GPU capacity and none is planned for FY26.

Modelyard runs in-region, and its training pipelines run in-region.

## Rules engine

The rules engine runs inside the same service as the routing request handler. It can be run in shadow alongside a second router: both produce a decision, one is applied, both are logged. Shadow mode has been used before, for the v3 rollout in November 2024.

## Ticket data

Ticket text is available in the warehouse from 2023-04 onward. Attachments are not, and roughly 9% of Technical Faults tickets carry a photograph the router cannot see.

## Analytics lag

Ticket events reach the analytics warehouse with a lag of up to 26 hours.
