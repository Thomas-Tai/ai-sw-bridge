ai-sw-bridge — read me first
============================

WHAT THIS IS
  A self-contained installer that puts ai-sw-bridge and its own private
  Python on your machine. You do NOT need to install Python yourself.

PREREQUISITE
  SOLIDWORKS must already be installed. ai-sw-bridge drives SOLIDWORKS via
  COM; this installer bundles Python, not SOLIDWORKS.

"WINDOWS PROTECTED YOUR PC" (SmartScreen)
  This installer is NOT code-signed (open-source, no certificate), so
  Windows SmartScreen will warn you. To proceed:
      1. Click "More info".
      2. Click "Run anyway".
  If you would rather not run an unsigned installer, use the pipx method
  below instead.

PREFER PYTHON/PIPX? (the trusted alternative)
  If you already have Python 3.10+ (or are willing to install it):
      pipx install git+https://github.com/Thomas-Tai/ai-sw-bridge
      ai-sw-doctor --register

AFTER INSTALL
  Open a NEW terminal and run:  ai-sw-build --list-kinds
  To wire the MCP server later:  ai-sw-doctor --register

INSTALL LOCATION
  %LOCALAPPDATA%\Programs\ai-sw-bridge  (per-user; no admin required)
