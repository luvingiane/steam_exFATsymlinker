#!/usr/bin/env python3
"""Interactive helper to sync Steam libraries on exFAT drives."""

from __future__ import annotations

import locale
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Optional


def detect_language() -> str:
    """Return the language code to use ("it" or "en")."""

    lang, _ = locale.getdefaultlocale() or ("", None)
    if isinstance(lang, str) and lang.lower().startswith("it"):
        return "it"
    return "en"


TEXT: Dict[str, Dict[str, str]] = {
    "en": {
        "welcome": "🚀 Steam exFAT Symlinker",
        "detected_mounts": "🔍 Detected exFAT Steam libraries:",
        "no_mounts": "⚠️  No exFAT Steam libraries found automatically.",
        "choose_path": "Select a library by number or type a custom path:",
        "manual_option": "[M] Enter a custom path",
        "enter_path": "Enter the full path to your steamapps folder: ",
        "invalid_choice": "❌ Invalid choice, please try again.",
        "path_not_found": "❌ The provided path does not exist or is not a directory.",
        "menu_title": "\nWhat do you want to do?",
        "menu_options": (
            "1) Update ACF symlinks\n"
            "2) Force ACF symlinks (dangerous)\n"
            "3) Fix SteamLinuxRuntime_sniper\n"
            "4) Export updated ACFs back to the exFAT drive\n"
            "Q) Quit"
        ),
        "prompt_choice": "Choose an option: ",
        "force_warning": "⚠️  This will remove existing files/folders before recreating links!",
        "confirm_force": "Type 'YES' to continue: ",
        "cancelled": "Operation cancelled.",
        "no_games": "❌ No appmanifest files found on the external drive.",
        "no_acf_local": "❌ No appmanifest files found in the local Steam folder.",
        "link_done": "✅ Symlinks updated.",
        "runtime_missing": "❌ SteamLinuxRuntime_sniper was not found on the external drive:",
        "runtime_copy": "📦 Copying runtime...",
        "runtime_done": "✅ SteamLinuxRuntime_sniper is ready.",
        "acf_export": "✅ Exported {count} manifest file(s) to the external drive.",
        "bye": "👋 Bye!",
        "status_already": "✅ Already linked: {name}",
        "status_replaced": "♻️  Replaced link: {name}",
        "status_removed": "⚠️  Removed existing path: {path}",
        "status_skip": "⛔ Existing object skipped (use forced option to overwrite): {path}",
        "status_linked": "🔗 Linked {name} → {src}",
        "missing_source": "❓ Missing source, skipping: {name}",
    },
    "it": {
        "welcome": "🚀 Steam exFAT Symlinker",
        "detected_mounts": "🔍 Librerie Steam su exFAT rilevate:",
        "no_mounts": "⚠️  Nessuna libreria Steam su exFAT trovata automaticamente.",
        "choose_path": "Seleziona una libreria con il numero oppure inserisci un percorso:",
        "manual_option": "[M] Inserisci un percorso manuale",
        "enter_path": "Percorso completo della cartella steamapps: ",
        "invalid_choice": "❌ Scelta non valida, riprova.",
        "path_not_found": "❌ Il percorso indicato non esiste oppure non è una cartella.",
        "menu_title": "\nCosa vuoi fare?",
        "menu_options": (
            "1) Aggiorna i symlink degli ACF\n"
            "2) Forza i symlink degli ACF (operazione rischiosa)\n"
            "3) Sistema SteamLinuxRuntime_sniper\n"
            "4) Esporta gli ACF aggiornati sul disco exFAT\n"
            "Q) Esci"
        ),
        "prompt_choice": "Scegli un'opzione: ",
        "force_warning": "⚠️  Questa operazione elimina file/cartelle esistenti prima di ricreare i link!",
        "confirm_force": "Scrivi 'YES' per continuare: ",
        "cancelled": "Operazione annullata.",
        "no_games": "❌ Nessun file appmanifest trovato sull'unità esterna.",
        "no_acf_local": "❌ Nessun file appmanifest trovato nella cartella Steam locale.",
        "link_done": "✅ Symlink aggiornati.",
        "runtime_missing": "❌ SteamLinuxRuntime_sniper non è stato trovato sul disco esterno:",
        "runtime_copy": "📦 Copia del runtime in corso...",
        "runtime_done": "✅ SteamLinuxRuntime_sniper pronto.",
        "acf_export": "✅ Esportati {count} manifest sul disco esterno.",
        "bye": "👋 Ciao!",
        "status_already": "✅ Già collegato: {name}",
        "status_replaced": "♻️  Link sostituito: {name}",
        "status_removed": "⚠️  Percorso esistente rimosso: {path}",
        "status_skip": "⛔ Oggetto esistente ignorato (usa l'opzione forzata per sovrascrivere): {path}",
        "status_linked": "🔗 Collegato {name} → {src}",
        "missing_source": "❓ Sorgente mancante, salto: {name}",
    },
}


def detect_exfat_mounts() -> List[Path]:
    """Return mount points that use an exFAT filesystem."""

    mounts: List[Path] = []
    exfat_names = {"exfat", "fuse.exfat", "exfat-fuse"}
    try:
        with open("/proc/mounts", "r", encoding="utf-8") as f:
            for line in f:
                parts = line.split()
                if len(parts) < 3:
                    continue
                mount_point = Path(parts[1])
                fs_type = parts[2].lower()
                if fs_type in exfat_names and mount_point.exists():
                    mounts.append(mount_point)
    except FileNotFoundError:
        pass
    return mounts


def discover_steamapps_paths(mounts: Iterable[Path]) -> List[Path]:
    """Return possible steamapps directories within the provided mounts."""

    candidates: List[Path] = []
    seen: set[Path] = set()

    def register(path: Path) -> None:
        if path.exists() and path.is_dir():
            resolved = path.resolve()
            if resolved not in seen:
                seen.add(resolved)
                candidates.append(path)

    for mount in mounts:
        register(mount / "SteamLibrary/steamapps")
        register(mount / "steamapps")
        register(mount / "Steam/steamapps")

        try:
            for entry in mount.iterdir():
                if not entry.is_dir():
                    continue
                if entry.name.lower() == "steamlibrary":
                    register(entry / "steamapps")
                elif entry.name.lower() == "steamapps":
                    register(entry)
                else:
                    # Check one level deeper for SteamLibrary/steamapps
                    try:
                        for sub in entry.iterdir():
                            if not sub.is_dir():
                                continue
                            if sub.name.lower() == "steamlibrary":
                                register(sub / "steamapps")
                            elif sub.name.lower() == "steamapps":
                                register(sub)
                    except PermissionError:
                        continue
        except PermissionError:
            continue

    return candidates


def choose_external_path(language: str) -> Optional[Path]:
    """Prompt the user to choose an external steamapps path."""

    text = TEXT[language]
    mounts = detect_exfat_mounts()
    candidates = discover_steamapps_paths(mounts)

    print(text["welcome"])
    if candidates:
        print(text["detected_mounts"])
        for idx, path in enumerate(candidates, 1):
            print(f"  {idx}) {path}")
    else:
        print(text["no_mounts"])

    while True:
        print(text["choose_path"])
        if candidates:
            print(text["manual_option"])
        raw_choice = input(text["prompt_choice"]) if candidates else "m"
        if not candidates or raw_choice.lower() in {"m", "manual", "manuale"}:
            custom = input(text["enter_path"]).strip()
            if not custom:
                return None
            path = Path(custom).expanduser()
            if path.exists() and path.is_dir():
                return path
            print(text["path_not_found"])
            continue
        try:
            idx = int(raw_choice)
        except (TypeError, ValueError):
            print(text["invalid_choice"])
            continue
        if 1 <= idx <= len(candidates):
            return candidates[idx - 1]
        print(text["invalid_choice"])


def parse_games(acf_files: Iterable[Path]) -> List[Dict[str, str]]:
    games: List[Dict[str, str]] = []
    for acf in acf_files:
        try:
            content = acf.read_text(errors="ignore")
        except OSError:
            continue
        name_match = re.search(r'"name"\s+"(.+?)"', content)
        folder_match = re.search(r'"installdir"\s+"(.+?)"', content)
        if name_match and folder_match:
            games.append({
                "acf": acf.name,
                "name": name_match.group(1),
                "folder": folder_match.group(1),
            })
    return games


def safe_symlink(src: Path, dst: Path, *, force: bool, text: Dict[str, str]) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        if dst.is_symlink():
            try:
                if dst.resolve() == src.resolve():
                    print(text["status_already"].format(name=dst.name))
                    return
            except FileNotFoundError:
                pass
            dst.unlink()
            print(text["status_replaced"].format(name=dst.name))
        else:
            if force:
                if dst.is_dir():
                    shutil.rmtree(dst)
                else:
                    dst.unlink()
                print(text["status_removed"].format(path=dst))
            else:
                print(text["status_skip"].format(path=dst))
                return
    dst.symlink_to(src, target_is_directory=src.is_dir())
    print(text["status_linked"].format(name=dst.name, src=src))


def update_symlinks(steamapps_ext: Path, steamapps_local: Path, *, force: bool, language: str) -> None:
    text = TEXT[language]
    acf_files = sorted(steamapps_ext.glob("appmanifest_*.acf"))
    games = parse_games(acf_files)
    if not games:
        print(text["no_games"])
        return

    common_ext = steamapps_ext / "common"
    common_local = steamapps_local / "common"
    common_local.mkdir(parents=True, exist_ok=True)

    for game in games:
        src_acf = steamapps_ext / game["acf"]
        dst_acf = steamapps_local / game["acf"]
        safe_symlink(src_acf, dst_acf, force=force, text=text)

        src_folder = common_ext / game["folder"]
        dst_folder = common_local / game["folder"]
        if src_folder.exists():
            safe_symlink(src_folder, dst_folder, force=force, text=text)
        else:
            print(text["missing_source"].format(name=game["folder"]))

    print(text["link_done"])


def ensure_runtime(steamapps_ext: Path, language: str) -> None:
    text = TEXT[language]
    runtime_src = steamapps_ext / "common/SteamLinuxRuntime_sniper"
    if not runtime_src.exists():
        print(f"{text['runtime_missing']} {runtime_src}")
        return

    runtime_dst = Path.home() / ".steam/runtime/SteamLinuxRuntime_sniper"
    runtime_dst.mkdir(parents=True, exist_ok=True)

    print(text["runtime_copy"])
    rsync_path = shutil.which("rsync")
    if rsync_path:
        subprocess.run(
            [
                rsync_path,
                "-a",
                "--delete",
                f"{runtime_src}/",
                str(runtime_dst),
            ],
            check=False,
        )
    else:
        if runtime_dst.exists():
            shutil.rmtree(runtime_dst)
        shutil.copytree(runtime_src, runtime_dst)

    steam_common = Path.home() / ".steam/steam/steamapps/common"
    steam_common.mkdir(parents=True, exist_ok=True)
    safe_symlink(runtime_dst, steam_common / "SteamLinuxRuntime_sniper", force=True, text=text)

    print(text["runtime_done"])


def export_acf_to_external(steamapps_ext: Path, steamapps_local: Path, language: str) -> None:
    text = TEXT[language]
    acf_files = sorted(steamapps_local.glob("appmanifest_*.acf"))
    if not acf_files:
        print(text["no_acf_local"])
        return

    count = 0
    for acf in acf_files:
        try:
            source = acf.resolve() if acf.is_symlink() else acf
        except FileNotFoundError:
            continue

        if not source.exists():
            continue

        destination = steamapps_ext / acf.name
        destination.parent.mkdir(parents=True, exist_ok=True)

        same_file = False
        if destination.exists():
            try:
                same_file = source.samefile(destination)
            except (FileNotFoundError, OSError):
                same_file = False

        if same_file:
            continue

        shutil.copy2(source, destination)
        count += 1

    print(text["acf_export"].format(count=count))


def main() -> None:
    language = detect_language()
    text = TEXT[language]

    steamapps_ext = choose_external_path(language)
    if steamapps_ext is None:
        print(text["bye"])
        return
    if not steamapps_ext.exists() or not steamapps_ext.is_dir():
        print(text["path_not_found"])
        return

    steamapps_local = Path.home() / ".steam/steam/steamapps"
    steamapps_local.mkdir(parents=True, exist_ok=True)

    while True:
        print(text["menu_title"])
        print(text["menu_options"])
        choice = input(text["prompt_choice"]).strip().lower()

        if choice == "1":
            update_symlinks(steamapps_ext, steamapps_local, force=False, language=language)
        elif choice == "2":
            print(text["force_warning"])
            confirm = input(text["confirm_force"]).strip().lower()
            if confirm == "yes":
                update_symlinks(steamapps_ext, steamapps_local, force=True, language=language)
            else:
                print(text["cancelled"])
        elif choice == "3":
            ensure_runtime(steamapps_ext, language)
        elif choice == "4":
            export_acf_to_external(steamapps_ext, steamapps_local, language)
        elif choice in {"q", "quit", "exit"}:
            print(text["bye"])
            break
        else:
            print(text["invalid_choice"])


if __name__ == "__main__":
    main()
