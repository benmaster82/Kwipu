"""Run the Kwipu bridge with its validated runtime configuration."""
from __future__ import annotations

import uvicorn

from . import config
from .app import app


def main() -> None:
    uvicorn.run(app, host=config.HOST, port=config.PORT)


if __name__ == "__main__":
    main()
