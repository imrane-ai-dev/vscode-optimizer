

import os
import psutil
import shutil
import zipfile
from pathlib import Path
from datetime import datetime
from typing import List, Tuple


class VSCodeOptimizer:
    def __init__(self):
        self.base_path, self.ext_path = self._discover_paths()

    def _discover_paths(self):
        # Discover paths from running VS Code processes first.
        user_data = None
        extensions = None

        for proc in psutil.process_iter(["name", "cmdline", "exe"]):
            try:
                name = (proc.info["name"] or "").lower()
                if name not in ("code.exe", "code - insiders.exe", "code"):
                    continue

                cmdline = proc.info.get("cmdline") or []

                for arg in cmdline:
                    if arg.startswith("--user-data-dir="):
                        user_data = Path(arg.split("=", 1)[1].strip('"'))
                    elif arg.startswith("--extensions-dir="):
                        extensions = Path(arg.split("=", 1)[1].strip('"'))

                # Portable VS Code stores data in a "data" folder
                # next to the executable.
                exe = proc.info.get("exe")
                if exe and not user_data:
                    portable_data = Path(exe).parent / "data"
                    if portable_data.is_dir():
                        user_data = portable_data / "user-data"
                        if not extensions:
                            extensions = portable_data / "extensions"

            except (psutil.NoSuchProcess, psutil.AccessDenied,
                    psutil.ZombieProcess, OSError):
                continue

        appdata = Path(os.environ.get(
            "APPDATA", str(Path.home() / "AppData" / "Roaming")
        ))
        localappdata = Path(os.environ.get(
            "LOCALAPPDATA",
            str(Path.home() / "AppData" / "Local")
        ))

        # Prefer the discovered paths, then standard Windows locations.
        if user_data is None:
            candidates = [
                appdata / "Code",
                appdata / "Code - Insiders",
                localappdata / "Programs" / "Microsoft VS Code" / "data" / "user-data",
                localappdata / "Programs" / "Microsoft VS Code Insiders" / "data" / "user-data",
            ]
            user_data = next(
                (p for p in candidates if p.is_dir()),
                appdata / "Code"
            )

        if extensions is None:
            candidates = [
                user_data / "extensions",
                Path.home() / ".vscode" / "extensions",
                Path.home() / ".vscode-insiders" / "extensions",
            ]
            extensions = next(
                (p for p in candidates if p.is_dir()),
                Path.home() / ".vscode" / "extensions"
            )

        return user_data, extensions

    def get_vscode_processes(self) -> Tuple[float, List[dict]]:
        processes = []
        total_ram = 0.0

        for proc in psutil.process_iter(
            ["pid", "name", "memory_info", "cmdline"]
        ):
            try:
                name = proc.info["name"] or ""
                if name.lower() not in (
                    "code.exe", "code - insiders.exe", "code"
                ):
                    continue

                # USS is private memory; RSS is the fallback.
                try:
                    memory = proc.memory_full_info()
                    ram_mb = getattr(
                        memory, "uss", memory.rss
                    ) / 1024 / 1024
                    metric = "USS" if hasattr(memory, "uss") else "RSS"
                except (psutil.AccessDenied, OSError):
                    memory = proc.info["memory_info"]
                    if memory is None:
                        continue
                    ram_mb = memory.rss / 1024 / 1024
                    metric = "RSS (fallback)"

                total_ram += ram_mb
                processes.append({
                    "pid": proc.info["pid"],
                    "name": name,
                    "ram_mb": ram_mb,
                    "metric": metric
                })

            except (psutil.NoSuchProcess, psutil.AccessDenied,
                    psutil.ZombieProcess, OSError):
                continue

        return total_ram, processes

    def analyze_extensions(self) -> List[Tuple[str, float]]:
        if not self.ext_path.is_dir():
            return []

        extensions = []

        for ext_dir in self.ext_path.iterdir():
            if not ext_dir.is_dir() or ext_dir.is_symlink():
                continue

            size_bytes = 0

            try:
                for f in ext_dir.rglob("*"):
                    try:
                        if f.is_file() and not f.is_symlink():
                            size_bytes += f.stat().st_size
                    except OSError:
                        continue
            except OSError:
                continue

            size_mb = size_bytes / 1024 / 1024
            if size_mb > 10:
                extensions.append((ext_dir.name, size_mb))

        return sorted(extensions, key=lambda x: x[1], reverse=True)

    def clean_cache(self) -> float:
        cache_dirs = [
            "Cache", "CachedData", "GPUCache",
            "Code Cache", "CachedExtensions", "logs"
        ]

        if not self.base_path.is_dir():
            print(f" [WARNING] Data directory not found: {self.base_path}")
            return 0.0

        # Avoid modifying active cache files.
        running = []
        for proc in psutil.process_iter(["name"]):
            try:
                name = (proc.info["name"] or "").lower()
                if name in ("code.exe", "code - insiders.exe", "code"):
                    running.append(proc.pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        if running:
            print(" [WARNING] VS Code appears to be running.")
            print(" Close all VS Code windows before cleaning.")
            return 0.0

        targets = []
        for name in cache_dirs:
            target = self.base_path / name
            if target.is_dir() and not target.is_symlink():
                targets.append((name, target))

        if not targets:
            print(" [INFO] No cache directories found.")
            return 0.0

        estimated_bytes = 0
        for _, target in targets:
            for f in target.rglob("*"):
                try:
                    if f.is_file() and not f.is_symlink():
                        estimated_bytes += f.stat().st_size
                except OSError:
                    continue

        print(f" Data directory: {self.base_path}")
        print(f" Estimated cache size: {estimated_bytes / 1024 / 1024:.1f} MB")
        print(" A ZIP backup will be created before deleting anything.")

        confirm = input(" Continue? (y/n): ").strip().lower()
        if confirm not in ("y", "yes"):
            print(" [CANCELLED] No files deleted.")
            return 0.0

        backup_dir = Path.home() / "Documents" / "VSCodeCacheBackups"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"vscode_cache_{timestamp}.zip"

        try:
            backup_dir.mkdir(parents=True, exist_ok=True)

            # Create the backup before any deletion.
            with zipfile.ZipFile(
                backup_file, "w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                for name, target in targets:
                    for f in target.rglob("*"):
                        try:
                            if f.is_file() and not f.is_symlink():
                                archive.write(
                                    f,
                                    arcname=str(Path(name) / f.relative_to(target))
                                )
                        except OSError:
                            raise

        except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
            try:
                if backup_file.exists():
                    backup_file.unlink()
            except OSError:
                pass

            print(f" [ERROR] Backup failed: {exc}")
            print(" [CANCELLED] Nothing was intentionally deleted.")
            return 0.0

        print(f" [BACKUP] Created: {backup_file}")

        total_freed = 0.0

        for name, target in targets:
            size_freed = 0

            # Delete files individually and count successful deletions.
            for f in list(target.rglob("*")):
                try:
                    if f.is_file() and not f.is_symlink():
                        size = f.stat().st_size
                        f.unlink()
                        size_freed += size
                except OSError:
                    continue

            # Remove empty subdirectories.
            for d in sorted(
                [p for p in target.rglob("*") if p.is_dir()
                 and not p.is_symlink()],
                key=lambda p: len(p.parts),
                reverse=True
            ):
                try:
                    d.rmdir()
                except OSError:
                    pass

            try:
                target.rmdir()
            except OSError:
                pass

            total_freed += size_freed / 1024 / 1024
            print(
                f" [CLEANED] {name:<20} "
                f"-> {size_freed / 1024 / 1024:.1f} MB deleted"
            )

        print(f" [BACKUP] Your backup is at: {backup_file}")
        return total_freed

    def run(self):
        print("=" * 60)
        print("VS Code Performance Optimizer v1.0")
        print("Professional Edition - Made in Morocco")
        print("=" * 60 + "\n")

        print(f"Data directory: {self.base_path}")
        print(f"Extensions directory: {self.ext_path}\n")

        total_ram, processes = self.get_vscode_processes()

        print("[1] Memory Analysis")
        print(
            f" Total measured memory: {total_ram:.1f} MB "
            f"across {len(processes)} processes"
        )

        for p in sorted(
            processes, key=lambda x: x["ram_mb"], reverse=True
        )[:5]:
            print(
                f" - {p['name']} (PID {p['pid']}): "
                f"{p['ram_mb']:.1f} MB [{p['metric']}]"
            )

        print(" Note: USS is private memory; RSS includes shared memory.")
        print()

        print("[2] Extension Analysis")
        print(" Extension sizes are disk usage, not RAM usage.")
        heavy_exts = self.analyze_extensions()

        if heavy_exts:
            for name, size in heavy_exts[:5]:
                print(f" - {name}: {size:.1f} MB on disk")
        else:
            print(" No heavy extensions found.")

        print()

        print("[3] Cache Cleaning")
        freed_disk = self.clean_cache()
        print(f" Total successfully deleted file size: {freed_disk:.1f} MB\n")

        print("=" * 60)
        print("REPORT")
        print("=" * 60)
        print(f"Measured memory: {total_ram:.1f} MB")
        print(f"Disk files deleted: {freed_disk:.1f} MB")
        print(
            f"Status: {'HIGH - Investigate processes' if total_ram > 800 else 'CHECKED'}"
        )
        print("Restart VS Code if memory usage is high.")
        print("Memory usage after restart is not guaranteed.")
        print("=" * 60)


def main():
    optimizer = VSCodeOptimizer()
    optimizer.run()


if __name__ == "__main__":
    main()
