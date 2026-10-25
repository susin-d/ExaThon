# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

React and TypeScript for the client, FastAPI for the API, a Redis-backed Python worker for orchestration, and Exasol as the durable analytical system of record. Docker Compose runs the application services while connecting to a separately managed Exasol deployment.

## Users

The primary user is an Internal Ombudsman or Principal Nodal Officer at one bank. They begin each day with a large complaint backlog and need to identify hidden complaints, investigate systemic causes, and record defensible review decisions.

## Product Purpose

The Complaint Root-Cause Engine reads complaint text inside Exasol, identifies tickets that may have been misclassified, groups them into stable process-failure clusters, and gives investigators a traceable path from an aggregate signal to the supporting tickets. Success means investigators find consequential root causes earlier and can explain every conclusion.

## Positioning

Unlike complaint trackers that report the categories entered by agents, the product re-evaluates the underlying customer language and preserves the evidence, model version, and human decision behind each finding.

## Operating Context

The first release ingests batches through an API or CSV import. A Redis worker orchestrates prompt scoring and periodic discovery, while analytical processing and complaint text remain in Exasol. Investigators work in a desktop-first evidence workspace and may confirm, dismiss, or reclassify a finding without mutating the original ticket.

## Capabilities and Constraints

- Phase one covers ingestion, scoring, stable clusters, drill-down, a recall-first review queue, pipeline status, and append-only review decisions.
- New tickets are queued for scoring; known-cluster assignment is prompt while new-cluster discovery is scheduled.
- The first release is single-user and private. It exposes an identity boundary but does not implement login.
- English is the only supported complaint language until representative multilingual training data exists.
- Text AI, natural-language questioning, regulatory exports, live CRM integration, and automated customer replies are deliberately outside the first vertical slice.

## Brand Commitments

The working name is “Complaint Root-Cause Engine.” The interface is an evidence-led operational workspace: dense but legible, restrained, explicit about freshness, and never styled as an executive KPI dashboard.

## Evidence on Hand

The project brief defines a synthetic Indian bank dataset with planted UPI reversal, ATM debit, fee, loan-reset, and escalation patterns. CFPB narratives may demonstrate robustness on real US complaint writing, but they must not be presented as validation of complaint-vs-query detection or RBI-ground prediction.

## Product Principles

- Show the evidence behind every aggregate.
- Preserve raw input and append human judgment.
- Prefer high recall while making uncertainty unmistakable.
- Keep clusters stable enough to audit across time.
- Separate demonstrated performance from illustrative or synthetic claims.

## Accessibility & Inclusion

The interface targets WCAG 2.2 AA, supports keyboard operation, never relies on color alone, and keeps summaries usable on small screens without claiming full mobile investigation parity.
