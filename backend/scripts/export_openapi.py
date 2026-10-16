"""Write the API's OpenAPI schema to a JSON file (used for frontend type generation)."""

import json
import sys
from pathlib import Path

from app.main import app

out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("openapi.json")
out.write_text(json.dumps(app.openapi(), indent=2) + "\n", encoding="utf-8")
print(f"Wrote {out}")
