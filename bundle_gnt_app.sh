#!/usr/bin/zsh
# This command bundles Python, PyWebView, pysword, and your HTML into one file
pyinstaller --onefile --noconsole --add-data "path/to/your/sword/mods:sword_modules" app.py
