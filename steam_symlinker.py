#!/usr/bin/env python3
import os
import re
import sys
from pathlib import Path

# === CONFIG ===
steamapps_ext = Path("/PATH/TO/YOUR/DRIVE")
steamapps_local = Path.home() / ".steam/steam/steamapps"

FORCE = "--force" in sys.argv  # se vuoi sovrascrivere directory/FILE reali

def safe_symlink(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        if dst.is_symlink():
            try:
                if dst.resolve() == src.resolve():
                    print(f"✅ Already connected: {dst.name}")
                    return
            except FileNotFoundError:
                # link rotto
                pass
            dst.unlink()
            print(f"♻️  Replaced link: {dst.name}")
        else:
            if FORCE:
                if dst.is_dir():
                    # ATTENZIONE: rimuove directory reale
                    for p in sorted(dst.rglob("*"), reverse=True):
                        if p.is_file() or p.is_symlink(): p.unlink()
                        elif p.is_dir(): p.rmdir()
                    dst.rmdir()
                else:
                    dst.unlink()
                print(f"⚠️  Removed: {dst}")
            else:
                print(f"⛔ Found extisting object (i don't touch): {dst} — use --force if you want to overwrite")
                return
    dst.symlink_to(src, target_is_directory=src.is_dir())
    print(f"🔗 Collegato: {dst.name} -> {src}")

# === CHECK ===
if not steamapps_ext.exists():
    print(f"❌ ERROR 404: external folder not found: {steamapps_ext}"); sys.exit(1)
if not steamapps_local.exists():
    steamapps_local.mkdir(parents=True, exist_ok=True)

# === PARSE ACF ===
acf_files = list(steamapps_ext.glob("appmanifest_*.acf"))
games = []
for acf in acf_files:
    content = acf.read_text(errors="ignore")
    name = re.search(r'"name"\s+"(.+?)"', content)
    folder = re.search(r'"installdir"\s+"(.+?)"', content)
    if name and folder:
        games.append({"acf": acf.name, "name": name.group(1), "folder": folder.group(1)})

# === LINK ACF ===
for g in games:
    safe_symlink(steamapps_ext / g["acf"], steamapps_local / g["acf"])

# === LINK CARTELLE COMMON ===
common_ext = steamapps_ext / "common"
common_local = steamapps_local / "common"
common_local.mkdir(parents=True, exist_ok=True)

for g in games:
    src = common_ext / g["folder"]
    dst = common_local / g["folder"]
    if src.exists():
        safe_symlink(src, dst)
    else:
        print(f"❓ Missing source, skip: {g['folder']}")

print("\n✅ Done. If Steam doesn't see something, run 'Verify Integrity' inside the game's properties.")
