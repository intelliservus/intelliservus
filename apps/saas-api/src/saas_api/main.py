from __future__ import annotations

from .app import create_app
from .common.config import load_config

app = create_app(load_config())
