#!/usr/bin/zsh
# This command bundles Python, PyWebView, pysword, and your HTML into one file
pyinstaller --onefile --noconsole --add-data "path/to/your/sword/mods:sword_modules" app.py


#or...
# Example: If SBLGNT module files are in /path/to/SBLGNT/
#pyinstaller --onefile --noconsole --add-data "/path/to/SBLGNT.conf:mods.d" --add-data "/path/to/SBLGNT.bbl:modules/texts" app.py
