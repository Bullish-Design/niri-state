# Decisions

- Apply runtime fixes in a coordinated patch to avoid partial lifecycle behavior changes.
- Preserve existing public surface and add new start API in additive way.
- Implement bootstrap failure semantics strictly: event-stream failure before bootstrap completion now raises `BootstrapError`.
- Keep unknown-event bootstrap health semantics policy-faithful by only auto-promoting to `LIVE` when still `BOOTSTRAPPING`.
- Use coordinator-based stale handling from store mutation loop to make `ResyncPolicy.AUTO` effective in production path.
