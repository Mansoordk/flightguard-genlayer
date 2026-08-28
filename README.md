# FlightGuard

FlightGuard is a GenLayer-powered flight disruption protection verifier.

It addresses a real trust problem: a deterministic smart contract cannot directly interpret live web evidence about whether a real-world flight was cancelled or delayed. FlightGuard uses a GenLayer Intelligent Contract to fetch an external source, ask an LLM to classify the evidence, and have validators independently reproduce the trust-critical decision.

## Workflow

1. User creates a policy with flight number, date, live status URL and protection amount.
2. The frontend sends a real GenLayer transaction.
3. The contract fetches the supplied live web page.
4. The LLM returns structured evidence and a decision.
5. Validators independently repeat the evaluation and must agree on the decision field.
6. The result is stored on-chain and shown by the frontend.

Decision rules: `1` = cancelled or delayed at least 120 minutes; `0` = on time or delayed less than 120 minutes; `-1` = insufficient or not-yet-determinable evidence.

## Important scope

This MVP is a claim-verification/protection demo, not a regulated insurance product and does not transfer real payout funds. The protection amount is stored as policy metadata.

## Files

- `contracts/flight_guard.py` — Intelligent Contract.
- `frontend/app/page.tsx` — complete UI and transaction lifecycle.
- `frontend/lib/genlayer.ts` — GenLayerJS reads, wallet connection and writes.
- `frontend/app/globals.css` — styling.

## Contract deployment

Deploy `contracts/flight_guard.py` in GenLayer Studio with no constructor parameters. Copy the resulting contract address.

## Frontend

From `frontend` run `npm install`.

Copy `.env.local.example` to `.env.local` and set:

`NEXT_PUBLIC_GENLAYER_CONTRACT_ADDRESS=YOUR_DEPLOYED_CONTRACT_ADDRESS`

Then run `npm run dev`.

The frontend is configured for Testnet Bradbury. Your wallet must be connected to the same GenLayer network.

For a real demonstration, use a live flight-status URL from an airline, airport or reputable flight-status provider that clearly exposes the flight number/date. Do not use a source you control to manufacture a result.

## Development notes

The current GenLayer documentation recommends linting and testing Intelligent Contracts before deployment, and using GenLayerJS for the frontend. The frontend waits for finalized transactions and checks the execution result instead of assuming a transaction hash means success.

## Future versions

- multiple independent evidence sources
- evidence hashing and provenance
- claim expiration
- actual escrow/payout settlement
- appeals/disputes
- notifications
- public verification pages
