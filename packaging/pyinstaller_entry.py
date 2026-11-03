"""PyInstaller entry point: the frozen app behaves exactly like the `mcp-browser` console script."""

from mcp_browser.cli import main

if __name__ == "__main__":
    main()
