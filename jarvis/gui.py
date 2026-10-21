"""J.A.R.V.I.S. Graphical User Interface Launcher.

Loads the Stark Industries Mark VII Arc Reactor HUD in a hardware-accelerated
desktop window using pywebview with full two-way Python-JavaScript bridging.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from .brain import Brain
from .config import Config
from .gui_bridge import JarvisGUIBridge
from .memory import Memory
from .utils import get_logger
from .voice_in import Listener
from .voice_out import Speaker

log = get_logger()


def launch_gui(
    brain: Brain,
    memory: Memory,
    config: Config,
    speaker: Optional[Speaker] = None,
    listener: Optional[Listener] = None,
    debug: bool = False,
) -> int:
    """Launch the Stark Industries Holographic Arc Reactor HUD."""
    try:
        import webview
    except ImportError:
        log.error("pywebview is not installed. Run 'pip install pywebview'.")
        print("ERROR: pywebview is required for GUI mode. Falling back to text mode.")
        return 1

    html_path = Path(__file__).resolve().parent / "web_gui" / "index.html"
    if not html_path.exists():
        log.error("GUI index.html not found at %s", html_path)
        print(f"ERROR: HUD interface template missing at {html_path}")
        return 1

    # Create the Python-JavaScript API Bridge
    bridge = JarvisGUIBridge(
        brain=brain,
        memory=memory,
        config=config,
        speaker=speaker,
        listener=listener,
    )

    try:
        window = webview.create_window(
            title="J.A.R.V.I.S. // STARK INDUSTRIES MARK VII",
            url=html_path.as_uri(),
            js_api=bridge,
            width=1280,
            height=820,
            min_size=(960, 600),
            background_color="#030710",
            text_select=False,
            zoomable=True,
        )

        bridge.set_window(window)

        # Start pywebview event loop
        webview.start(debug=debug)

    except Exception as exc:
        log.error("Failed to start pywebview GUI: %s", exc, exc_info=True)
        print(f"WARNING: GUI startup encountered an issue ({exc}).")
        bridge.close()
        return 1
    finally:
        bridge.close()

    return 0
