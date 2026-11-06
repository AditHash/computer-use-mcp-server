"""Minimal audit records. Never serialize tool arguments or backend errors."""
import json
import sys
from datetime import UTC, datetime


def emit(action: str, target_id: str, decision: str, result: str) -> None:
    record = {'time': datetime.now(UTC).isoformat(), 'action': action,
              'target': target_id, 'decision': decision, 'result': result}
    sys.stderr.write(json.dumps(record, separators=(',', ':')) + '\n')
    sys.stderr.flush()
