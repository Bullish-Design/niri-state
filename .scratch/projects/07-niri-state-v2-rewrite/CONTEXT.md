# CONTEXT

Working branch: `v2-rewrite`

Step 2 complete:
- reducer semantics now align with generated event contracts
- reconcile and invariant enforcement expanded to contract-critical paths
- deterministic ordering guarantees are now checked and tested
- targeted unit tests pass for reducers/reconcile/invariants/snapshot indexes

Next:
- Step 3 runtime lifecycle seams
- verify bootstrap buffering during query phase and correct initial revision publication
- tighten store mutation loop bootstrap/install/start/stop sequencing
