#!/usr/bin/env bash
set -euo pipefail

copilot=""
seq=""
run_id=""
result=""
summary=""
next_actions=""
evidence_paths=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --copilot)
      copilot="${2:-}"
      shift 2
      ;;
    --seq)
      seq="${2:-}"
      shift 2
      ;;
    --run-id)
      run_id="${2:-}"
      shift 2
      ;;
    --result)
      result="${2:-}"
      shift 2
      ;;
    --summary)
      summary="${2:-}"
      shift 2
      ;;
    --next_actions)
      next_actions="${2:-}"
      shift 2
      ;;
    --evidence_paths)
      evidence_paths="${2:-}"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if [[ -z "$copilot" || -z "$seq" || -z "$run_id" || -z "$result" ]]; then
  echo "Missing required arguments." >&2
  exit 2
fi

safe_copilot="${copilot// /_}"
out_path="copilots/${safe_copilot}_latest.md"

{
  echo "# Copilot Report"
  echo
  printf -- "- Copilot: %s\n" "$copilot"
  printf -- "- Seq: %s\n" "$seq"
  printf -- "- Run ID: %s\n" "$run_id"
  printf -- "- Result: %s\n" "$result"
  echo
  echo "## Summary"
  echo "$summary"
  echo
  echo "## Next Actions"
  echo "$next_actions"
  echo
  echo "## Evidence Paths"
  echo "$evidence_paths"
} > "$out_path"

echo "$out_path"
