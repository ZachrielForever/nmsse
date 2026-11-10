"""Timestamped, checksummed backups -- never edit without one."""
import hashlib
import shutil
from datetime import datetime
from pathlib import Path

BACKUP_DIRNAME = ".nmsedit-backups"


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def make_backup(save_path):
    d = Path(save_path).parent / BACKUP_DIRNAME
    d.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dst = d / f"{Path(save_path).name}.{stamp}.bak"
    shutil.copy2(save_path, dst)
    manifest = d / "SHA256SUMS"
    with manifest.open("a") as f:
        f.write(f"{sha256_file(dst)}  {dst.name}\n")
    return str(dst)


def list_backups(save_path):
    d = Path(save_path).parent / BACKUP_DIRNAME
    if not d.is_dir():
        return []
    return sorted(
        ({"path": str(f), "name": f.name, "size": f.stat().st_size}
         for f in d.glob("*.bak")),
        reverse=True,
    )


def restore(save_path, backup_path):
    make_backup(save_path)  # snapshot current state too
    shutil.copy2(backup_path, save_path)