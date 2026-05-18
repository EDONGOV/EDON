"""Static UI mounting for the EDON Gateway.

Mounts the React console UI (or simple HTML fallback) at /ui and the
voice meeting interface at /voice. Both are optional — missing directories
are handled gracefully so the gateway starts regardless of build state.
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .config import config
from .logging_config import get_logger

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = get_logger(__name__)


def mount_static_ui(app: "FastAPI") -> None:
    """Mount all static UI surfaces onto app."""
    _mount_console_ui(app)
    _mount_voice_ui(app)


def _mount_console_ui(app: "FastAPI") -> None:
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    try:
        ui_path = Path(__file__).parent / "ui"
        console_ui_dist = ui_path / "console-ui" / "dist"
        simple_ui_html = ui_path / "index.html"

        if console_ui_dist.exists() and (console_ui_dist / "index.html").exists():
            app.mount("/ui", StaticFiles(directory=str(console_ui_dist), html=True), name="ui")
            app.mount(
                "/assets",
                StaticFiles(directory=str(console_ui_dist / "assets")),
                name="assets",
            )

            @app.get("/")
            async def root():
                return FileResponse(str(console_ui_dist / "index.html"))

        elif simple_ui_html.exists():
            app.mount("/ui", StaticFiles(directory=str(ui_path), html=True), name="ui")

            @app.get("/")
            async def root():  # type: ignore[misc]
                return FileResponse(str(simple_ui_html))

        else:
            if not config.is_production() or config.BUILD_UI:
                logger.warning("No UI found. Run setup_ui.sh or setup_ui.ps1 to set up React UI")
    except Exception as exc:
        logger.warning("Could not mount console UI: %s", exc)


def _mount_voice_ui(app: "FastAPI") -> None:
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    try:
        static_dir = Path(__file__).parent / "static"
        if static_dir.exists():
            app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

            @app.get("/voice")
            async def voice_ui():
                return FileResponse(str(static_dir / "voice.html"))
    except Exception as exc:
        logger.warning("Could not mount voice UI: %s", exc)
