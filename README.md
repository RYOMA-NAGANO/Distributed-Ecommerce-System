# ERSS Final Project (Mini Amazon + Mini UPS + World)

This repository contains a split implementation of:
- Amazon web app + daemon (`amazon/`)
- UPS web app + daemon (`docker-deploy/web-app/`)
- World simulator deployment (`docker_deploy_world/`)

## Start Order

1. Start World with flakiness `0` first:
```bash
cd docker_deploy_world
WORLD_FLAKINESS=0 docker compose up --build
```
2. Start Amazon and UPS stacks.
3. After seqnum/ack behavior is verified, restart World with a non-zero flakiness value (for example `20`) to test dropped-request handling.

`WORLD_FLAKINESS` controls how often World drops requests.

## Seqnum / ACK Rules

- `seqnum` is per-sender and monotonically increasing.
- Amazon and World keep separate seqnum streams.
- ACK for a received command uses the exact same seqnum as that command.
  - Example: if Amazon sends `APurchaseMore(seqnum=13)`, World ACKs with `13`.
- World response messages (`arrived`, `ready`, `loaded`, etc.) carry World-owned response seqnums, independent from Amazon command seqnums.
- ACKs may be piggybacked on other outbound messages or sent alone.

So yes: acknowledging message `101` means sending ACK `101`.

## Flakiness Note

Think of flakiness as how often the world behaves "stupidly" and ignores a request.
With flakiness enabled, ACK is the delivery guarantee mechanism:
- sender keeps retrying unacked seqnums
- receiver deduplicates by seqnum and stays idempotent

Amazon daemon retry tuning (optional):
- `ACK_RETRY_INTERVAL_SECONDS` (default `5`)
- `ACK_MAX_RETRIES` (default `200`)

## World Time Behavior

World time continues in real time even if clients disconnect.
If you dispatch work, disconnect, and reconnect hours later, package/truck state can advance during that wall-clock gap.
