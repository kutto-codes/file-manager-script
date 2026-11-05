# file-manager-script
This is a simple file management automation script 
Commands:
  organize  Sort files in a folder into subfolders (by type or by date)
  dupes     Find (and optionally delete) duplicate files
  old       Find (and optionally delete) files older than N days
  undo      Undo the last 'organize' run

# Examples:
  python3 fm.py organize ~/Downloads --dry-run
  python3 fm.py organize ~/Downloads
  python3 fm.py organize ~/Downloads --by date
  python3 fm.py dupes ~/Documents
  python3 fm.py dupes ~/Documents --delete
  python3 fm.py old ~/Downloads --days 60
  python3 fm.py undo


import argparse
import hashlib
import json
import shutil
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
 
