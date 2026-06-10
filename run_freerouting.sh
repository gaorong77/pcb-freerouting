#!/usr/bin/env bash
# Run full pipeline: pcb_data.json -> board.dsn -> board.ses -> routing_result.json
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

JAR="${1:-freerouting.jar}"

echo "=== Step 1: Convert pcb_data.json -> board.dsn ==="
python pcb_to_dsn.py pcb_data.json board.dsn

echo "=== Step 2: Run Freerouting (DSN -> SES) ==="
java -jar "$JAR" -de board.dsn -do board.ses -mp 100

echo "=== Step 3: Parse SES -> routing_result.json ==="
python ses_parser.py board.ses routing_result.json

echo "=== Done! Open viewer.html to view results ==="
