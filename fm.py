#!/usr/bin/env python3
"""
fm.py - simple file management automation.

Commands:
  organize  Sort files in a folder into subfolders (by type or by date)
  dupes     Find (and optionally delete) duplicate files
  old       Find (and optionally delete) files older than N days
  undo      Undo the last 'organize' run

Examples:
  python3 fm.py organize ~/Downloads --dry-run
  python3 fm.py organize ~/Downloads
  python3 fm.py organize ~/Downloads --by date
  python3 fm.py dupes ~/Documents
  python3 fm.py dupes ~/Documents --delete
  python3 fm.py old ~/Downloads --days 60
  python3 fm.py undo
"""

import argparse
import hashlib
import json
import shutil
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

LOG_FILE = Path.home() / ".fm_last_run.json"

CATEGORIES = {
    "Images":    {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".heic"},
    "Documents": {".pdf", ".doc", ".docx", ".txt", ".odt", ".rtf", ".md", ".epub"},
    "Sheets":    {".xls", ".xlsx", ".csv", ".ods"},
    "Slides":    {".ppt", ".pptx", ".odp"},
    "Videos":    {".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv"},
    "Audio":     {".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"},
    "Archives":  {".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar", ".tgz"},
    "Code":      {".py", ".js", ".ts", ".html", ".css", ".java", ".c", ".cpp",
                  ".sh", ".json", ".yml", ".yaml", ".sql"},
    "Installers": {".deb", ".rpm", ".appimage", ".iso", ".run"},
}


def category_for(path: Path) -> str:
    ext = path.suffix.lower()
    for name, exts in CATEGORIES.items():
        if ext in exts:
            return name
    return "Other"


def unique_destination(dest: Path) -> Path:
    """If dest exists, append _1, _2, ... so nothing is overwritten."""
    if not dest.exists():
        return dest
    i = 1
    while True:
        candidate = dest.with_name(f"{dest.stem}_{i}{dest.suffix}")
        if not candidate.exists():
            return candidate
        i += 1


def human_size(num: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num < 1024:
            return f"{num:.1f} {unit}"
        num /= 1024
    return f"{num:.1f} TB"


def confirm(prompt: str) -> bool:
    return input(f"{prompt} [y/N] ").strip().lower() == "y"


# ---------------------------------------------------------------- organize
def cmd_organize(args):
    folder = Path(args.folder).expanduser().resolve()
    if not folder.is_dir():
        sys.exit(f"Not a folder: {folder}")

    moves = []
    for item in sorted(folder.iterdir()):
        if not item.is_file() or item.name.startswith("."):
            continue
        if args.by == "date":
            stamp = datetime.fromtimestamp(item.stat().st_mtime)
            sub = stamp.strftime("%Y-%m")
        else:
            sub = category_for(item)
        dest = unique_destination(folder / sub / item.name)
        moves.append((item, dest))

    if not moves:
        print("Nothing to organize.")
        return

    for src, dest in moves:
        print(f"{src.name}  ->  {dest.parent.name}/{dest.name}")

    if args.dry_run:
        print(f"\nDry run: {len(moves)} file(s) would be moved.")
        return

    done = []
    for src, dest in moves:
        dest.parent.mkdir(exist_ok=True)
        shutil.move(str(src), str(dest))
        done.append({"from": str(src), "to": str(dest)})

    LOG_FILE.write_text(json.dumps(done, indent=2))
    print(f"\nMoved {len(done)} file(s). Run 'undo' to reverse.")


def cmd_undo(_args):
    if not LOG_FILE.exists():
        sys.exit("No previous organize run to undo.")
    moves = json.loads(LOG_FILE.read_text())
    restored = 0
    for m in reversed(moves):
        src, dest = Path(m["to"]), Path(m["from"])
        if src.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(unique_destination(dest)))
            restored += 1
    LOG_FILE.unlink()
    print(f"Restored {restored} file(s).")


# ------------------------------------------------------------------ dupes
def file_hash(path: Path, chunk=1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def cmd_dupes(args):
    folder = Path(args.folder).expanduser().resolve()
    if not folder.is_dir():
        sys.exit(f"Not a folder: {folder}")

    # Group by size first (cheap), then hash only same-size files
    by_size = defaultdict(list)
    for p in folder.rglob("*"):
        if p.is_file() and not p.is_symlink():
            by_size[p.stat().st_size].append(p)

    by_hash = defaultdict(list)
    for size, paths in by_size.items():
        if len(paths) < 2 or size == 0:
            continue
        for p in paths:
            try:
                by_hash[file_hash(p)].append(p)
            except OSError:
                pass

    groups = [sorted(g, key=lambda p: p.stat().st_mtime) for g in by_hash.values() if len(g) > 1]
    if not groups:
        print("No duplicates found.")
        return

    wasted = 0
    to_delete = []
    for g in groups:
        keep, extras = g[0], g[1:]
        print(f"\nKeep:   {keep}")
        for e in extras:
            print(f"Dupe:   {e}")
            wasted += e.stat().st_size
            to_delete.append(e)

    print(f"\n{len(to_delete)} duplicate file(s), {human_size(wasted)} reclaimable.")

    if args.delete and confirm("Delete the duplicates listed above?"):
        for e in to_delete:
            e.unlink()
        print("Deleted.")


# -------------------------------------------------------------------- old
def cmd_old(args):
    folder = Path(args.folder).expanduser().resolve()
    if not folder.is_dir():
        sys.exit(f"Not a folder: {folder}")

    cutoff = time.time() - args.days * 86400
    old_files = [p for p in folder.rglob("*")
                 if p.is_file() and not p.is_symlink() and p.stat().st_mtime < cutoff]

    if not old_files:
        print(f"No files older than {args.days} days.")
        return

    total = 0
    for p in sorted(old_files):
        size = p.stat().st_size
        total += size
        age = (time.time() - p.stat().st_mtime) / 86400
        print(f"{age:6.0f} days  {human_size(size):>10}  {p}")

    print(f"\n{len(old_files)} file(s), {human_size(total)} total.")

    if args.delete and confirm("Delete these files?"):
        for p in old_files:
            p.unlink()
        print("Deleted.")


# ------------------------------------------------------------------- main
def main():
    parser = argparse.ArgumentParser(description="File management automation")
    sub = parser.add_subparsers(dest="command", required=True)

    o = sub.add_parser("organize", help="sort files into subfolders")
    o.add_argument("folder", nargs="?", default="~/Downloads")
    o.add_argument("--by", choices=["type", "date"], default="type")
    o.add_argument("--dry-run", action="store_true", help="preview only")
    o.set_defaults(func=cmd_organize)

    d = sub.add_parser("dupes", help="find duplicate files")
    d.add_argument("folder", nargs="?", default=".")
    d.add_argument("--delete", action="store_true", help="offer to delete duplicates")
    d.set_defaults(func=cmd_dupes)

    a = sub.add_parser("old", help="find old files")
    a.add_argument("folder", nargs="?", default="~/Downloads")
    a.add_argument("--days", type=int, default=30)
    a.add_argument("--delete", action="store_true", help="offer to delete them")
    a.set_defaults(func=cmd_old)

    u = sub.add_parser("undo", help="undo last organize run")
    u.set_defaults(func=cmd_undo)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
