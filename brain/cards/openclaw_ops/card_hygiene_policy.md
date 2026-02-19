# Card: Workspace Hygiene Policy

id: card-openclaw-hygiene-policy-001
type: principle
tags: hygiene,policy,sensitive
source_ref: state/workspace_hygiene_policy.json; scripts/workspace_hygiene_doctor.py; scripts/home_hygiene_doctor.py
status: active
confidence: 0.93
last_confirmed_at: 2026-02-18

## Summary

La politica versionada clasifica canon/tooling/junk/sensitive y define clean no-destructivo.

## How to apply

Ejecutar scan antes de clean, respetar max_moves y no tocar dot-dirs en home hygiene.
