# Card: Brain Indexer Behavior

id: card-openclaw-indexer-behavior-001
type: procedure
tags: brain,indexer,performance
source_ref: scripts/brain_index_build.py; state/workspace_hygiene_policy.json
status: active
confidence: 0.91
last_confirmed_at: 2026-02-18

## Summary

El indexer trabaja sobre namespace `brain` y excluye tooling, quarantine y salvage via policy + hard excludes.

## How to apply

Regenerar con `python3 scripts/brain_index_build.py` y responder usando registry en vez de leer vault/raw.
