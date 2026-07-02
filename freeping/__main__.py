from __future__ import annotations

import sys


def main() -> None:
    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        print("FreePing v0.1.0 - Tu NoPing personal")
        print()
        print("Usage:")
        print("  freeping            Start GUI (if available)")
        print("  freeping --cli      Start CLI mode")
        print("  freeping --help     Show this help")
        return

    if "--cli" in args:
        _run_cli()
        return

    try:
        from freeping.gui.app import launch_gui
        launch_gui()
    except ImportError:
        print("GUI mode requires PySide6. Install with: pip install freeping[gui]")
        print("Falling back to CLI mode...")
        _run_cli()


def _run_cli() -> None:
    from freeping.core.config import AppConfig
    config = AppConfig.load()
    status = "configured" if config.vps_ip else "not configured"
    print("FreePing v0.1.0")
    print(f"Status: {status}")
    if config.vps_ip:
        print(f"VPS: {config.vps_ip}")
    else:
        print("Run with GUI to configure your VPS.")


if __name__ == "__main__":
    main()
