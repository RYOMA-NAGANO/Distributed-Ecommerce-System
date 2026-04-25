# UPS Danger Log

- UPS callbacks to Amazon currently create a new `Idempotency-Key` on each retry, which can increase duplicate-event risk during network failures.
- UPS tests are tied to Docker-style DB host settings (`db`), so running tests directly on host often fails without extra configuration.
- Some shipment state transitions across callbacks can still be too permissive, making it easier for out-of-order updates to be accepted.
- Callback timeout and retry behavior can create noisy logs and repeated processing attempts, which makes debugging harder during demos.
- UPS depends on Amazon callback availability, so some flows can stall when Amazon is slow or temporarily unavailable.
- Error responses are not always consistent in detail, which can slow down root-cause analysis during integration failures.
- Local environment differences (ports, hostnames, secrets) can cause cross-machine integration drift.
- Asynchronous world events can still expose race conditions under high flakiness or reconnect scenarios.
