# CONTEXT

Working branch: `v2-rewrite`

Step 1 has been completed at the scaffolding/alignment level:
- skeleton code blocks were materialized for new v2 modules and tests
- `protocol.py` now imports `UnknownEvent` from `niri_pypc.types.base`
- typed model factory payloads were updated toward actual generated upstream model fields
- new typed factory files were added for events and fake connection bundles

Next immediate work is Step 2:
- correct reducer event field semantics (notably urgency/layout/focus/workspace activation contracts)
- complete reconcile and invariant logic per mandatory appendix contracts
- then commit/push step 2
