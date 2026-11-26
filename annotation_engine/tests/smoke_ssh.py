"""Headless smoke test for SSH (remote) projects: schema, client, fetch, sync."""
import os
import sqlite3
import stat
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

TMP = Path(tempfile.mkdtemp(prefix="ae_ssh_"))

import annotation_engine.config as config
config.DATABASE_PATH = TMP / "test.db"
config.PROJECTS_DIR = TMP / "projects"
config.SSH_CACHE_DIR = TMP / "ssh_cache"
config.SSH_CACHE_DIR.mkdir(parents=True, exist_ok=True)
import annotation_engine.core.database as dbm
dbm.DATABASE_PATH = config.DATABASE_PATH

from PySide6.QtWidgets import QApplication

app = QApplication([])
failures = []


def check(name, cond, extra=""):
    if cond:
        print(f"PASS {name}")
    else:
        print(f"FAIL {name} {extra}")
        failures.append(name)


# ------------------------------------------------------------- schema migration
old_db = TMP / "old.db"
conn = sqlite3.connect(old_db)
conn.execute(
    "CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT, description TEXT, "
    "base_path TEXT, created_at TIMESTAMP, updated_at TIMESTAMP)"
)
conn.commit()
conn.close()

from annotation_engine.core.database import Database

migrated = Database(old_db)
cols = {row["name"] for row in migrated.fetch_all("PRAGMA table_info(projects)")}
check("migration adds remote columns",
      {"remote_host", "remote_port", "remote_user", "remote_dir",
       "remote_secret"} <= cols, cols)


# -------------------------------------------------------------- remote project
from annotation_engine.core.database import (
    add_image, create_remote_project, get_project, get_project_images,
)

cache = TMP / "cache"
pid = create_remote_project(
    "Remote", cache, "127.0.0.1", 22, "user", "/data/images", "secret",
)
project = get_project(pid)
check("remote project stored", project["remote_host"] == "127.0.0.1"
      and project["remote_user"] == "user" and project["remote_dir"] == "/data/images",
      project)
check("remote project cache is base_path",
      Path(project["base_path"]) == cache, project["base_path"])
img_id = add_image(pid, "a.jpg", "sub/a.jpg", None, None, 123, None)
image = get_project_images(pid)[0]
check("remote image keeps relative path", image["relative_path"] == "sub/a.jpg")


# ------------------------------------------------------------- secret roundtrip
from annotation_engine.services.ssh_client import (
    SSHClient, decode_secret, encode_secret,
)

password, key_file = decode_secret(encode_secret("hunter2", "/keys/id_rsa"))
check("secret password roundtrip", password == "hunter2", password)
check("secret key file roundtrip", key_file == "/keys/id_rsa", key_file)


# ------------------------------------------------------------- fake SFTP client
class FakeAttr:
    def __init__(self, filename, st_mode=stat.S_IFREG | 0o644, st_size=0):
        self.filename = filename
        self.st_mode = st_mode
        self.st_size = st_size


class FakeSFTP:
    def __init__(self, tree):
        self.tree = tree            # remote dir -> [FakeAttr]
        self.files = {}             # remote file -> bytes
        self.downloads = []
        self.uploads = []
        self.created = []
        self.removed = []

    def listdir_attr(self, path):
        return list(self.tree.get(path, []))

    def get(self, remote, local):
        data = self.files.get(remote)
        if data is None:
            raise IOError(f"no such file: {remote}")
        with open(local, "wb") as handle:
            handle.write(data)
        self.downloads.append(remote)

    def put(self, local, remote):
        with open(local, "rb") as handle:
            self.files[remote] = handle.read()
        self.uploads.append(remote)

    def stat(self, path):
        if path in self.tree or path in self.files:
            return object()
        raise IOError("missing")

    def mkdir(self, path):
        self.created.append(path)

    def remove(self, path):
        self.removed.append(path)

    def rename(self, src, dst):
        if src in self.files:
            self.files[dst] = self.files.pop(src)

    def close(self):
        pass


tree = {
    "/data": [FakeAttr("a.jpg"), FakeAttr("notes.txt"),
              FakeAttr("sub", stat.S_IFDIR | 0o755)],
    "/data/sub": [FakeAttr("b.png")],
}
sftp = FakeSFTP(tree)
sftp.files["/data/a.jpg"] = b"JPEG-A"
sftp.files["/data/sub/b.png"] = b"PNG-B"

client = SSHClient("h", 22, "u")
client._sftp = sftp   # bypass connect()

listed = client.list_images("/data", recursive=True)
check("list_images finds nested images only",
      sorted(listed) == sorted([("a.jpg", 0), ("sub/b.png", 0)]), listed)

local_img = TMP / "out" / "a.jpg"
check("fetch downloads file", client.fetch("/data/a.jpg", local_img)
      and local_img.read_bytes() == b"JPEG-A")

ok = client.upload(local_img, "/data/labels/a.json")
check("upload writes payload",
      ok and sftp.files.get("/data/labels/a.json") == b"JPEG-A")
check("upload creates remote labels dir", "/data/labels" in sftp.created,
      sftp.created)

client._sftp = sftp
check("list ignores non-images", all(p.endswith((".jpg", ".png")) for p, _ in listed))

# ---------------------------------------------------------- upload_tree
staging = TMP / "staging"
(staging / "yolo" / "labels" / "train").mkdir(parents=True, exist_ok=True)
(staging / "yolo" / "images" / "train").mkdir(parents=True, exist_ok=True)
(staging / "yolo" / "labels" / "train" / "a.txt").write_text("0 0.5 0.5 0.2 0.2")
(staging / "yolo" / "images" / "train" / "a.png").write_bytes(b"PNG")
(staging / "yolo" / "data.yaml").write_text("path: /srv\n")

progress_events = []
uploaded = client.upload_tree(
    staging, "/srv/export", progress_callback=lambda p, m: progress_events.append(p)
)
check("upload_tree uploads every file", uploaded == 3, uploaded)
check("upload_tree preserves nested paths",
      sftp.files.get("/srv/export/yolo/labels/train/a.txt") == b"0 0.5 0.5 0.2 0.2",
      sorted(k for k in sftp.files if k.startswith("/srv/export")))
check("upload_tree creates nested remote dirs",
      "/srv/export/yolo/labels/train" in sftp.created, sftp.created)
check("upload_tree reports progress",
      bool(progress_events) and progress_events[-1] == 100, progress_events)
check("upload_tree empty dir uploads nothing",
      client.upload_tree(TMP / "empty_none", "/srv/none") == 0)


# --------------------------------------------------- window: fetch on demand
import annotation_engine.ui.main_window as mw

mw.MainWindow.showWelcomeDialog = lambda self: None
mw.MainWindow._prewarmAutoAnnotate = lambda self: None

_messages = []


def _record(kind):
    def handler(parent, title, text, *a, **k):
        _messages.append((kind, text))
        return 0
    return handler


mw.QMessageBox.warning = staticmethod(_record("warning"))
mw.QMessageBox.critical = staticmethod(_record("critical"))
mw.QMessageBox.information = staticmethod(_record("info"))

window = mw.MainWindow()
window.current_project_id = pid

fetches = []


class FakeRemoteClient:
    def fetch(self, remote_path, local_path):
        fetches.append(remote_path)
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        Path(local_path).write_bytes(b"CACHED")
        return True

    def upload(self, local_path, remote_path):
        sftp.files[remote_path] = Path(local_path).read_bytes()
        sftp.uploads.append(remote_path)
        return True

    def close(self):
        pass


window.sshClientForProject = lambda project_id: FakeRemoteClient()
window._newSshClient = lambda project_id: FakeRemoteClient()

remote_image = dbm.get_image(img_id)
path = window.ensure_local_image(remote_image)
check("remote image fetched on demand",
      path is not None and Path(path).exists(), path)
check("fetch used remote dir", fetches == ["/data/images/sub/a.jpg"], fetches)
fetches.clear()
path2 = window.ensure_local_image(remote_image)
check("cached image is not refetched", path2 == path and fetches == [], fetches)

# Local project behaves exactly as before (no SSH involved).
local_pid = dbm.create_project("Local", TMP / "projects")
local_base = Path(dbm.get_project(local_pid)["base_path"])
(local_base / "images").mkdir(parents=True, exist_ok=True)
(local_base / "images" / "x.png").write_bytes(b"x")
local_id = dbm.add_image(local_pid, "x.png", "images/x.png", 10, 10, 1, None)
window.current_project_id = local_pid
local_path = window.ensure_local_image(dbm.get_image(local_id))
check("local project returns local path", Path(local_path).exists(), local_path)


# ------------------------------------------- sync button visibility (SSH only)
window.loadProject(pid)
check("sync button visible for SSH project",
      window.toolbar.sync_action.isVisible(), window.toolbar.sync_action.isVisible())
window.loadProject(local_pid)
check("sync button hidden for local project",
      not window.toolbar.sync_action.isVisible())


# ------------------------------------------ non-blocking thumbnail + backfill
from annotation_engine.ui.widgets.image_grid import ImageGridModel
from PySide6.QtGui import QColor, QPixmap

window.loadProject(pid)
fetches.clear()
# A fresh, never-fetched image so the prefetch path is exercised.
uncached_id = dbm.add_image(pid, "uncached.jpg", "sub/uncached.jpg",
                            None, None, 10, None)
uncached = dbm.get_image(uncached_id)
model = ImageGridModel([uncached])
# New model instance with prefetch callback only (no blocking fetcher).
prefetch_requests = []
model.setPrefetchRequest(lambda image: prefetch_requests.append(image['id']) or True)
thumb = model.getThumbnail(uncached)
check("paint does not fetch remote image", fetches == [], fetches)
check("paint enqueues a prefetch instead", prefetch_requests == [uncached_id],
      prefetch_requests)
check("paint returns no pixmap while fetching", thumb is None)

# A completed prefetch backfills dimensions and invalidates the thumbnail.
real_pm = QPixmap(120, 90)
real_pm.fill(QColor("white"))
real_file = TMP / "real.png"
real_pm.save(str(real_file))
dbm.update_image(img_id, width=None, height=None)
window._onThumbnailReady(img_id, str(real_file), 120, 90)
refreshed = dbm.get_image(img_id)
check("prefetch backfills dimensions",
      refreshed["width"] == 120 and refreshed["height"] == 90, refreshed)


# ------------------------------------------------ overlay scaling regression
annotations = {img_id: [
    {"label": "box", "shape_type": "rectangle", "points": [[10, 10], [100, 80]]},
    {"label": "kp", "shape_type": "point", "points": [[50, 45]]},
    {"label": "obb", "shape_type": "oriented_rectangle",
     "points": [[10, 10], [100, 10], [100, 80], [10, 80]]},
]}
model.setAnnotationData(
    annotations=annotations,
    label_colors={"box": "#ff0000", "kp": "#00ff00", "obb": "#0000ff"},
    label_visibility={"box": True, "kp": True, "obb": True},
)
# Point the model at a local project so the file resolves without SSH.
model.setImages([{**dbm.get_image(img_id),
                  "project_id": local_pid,
                  "relative_path": "images/sub/a.jpg"}])
local_cache = Path(dbm.get_project(local_pid)["base_path"]) / "images"
local_cache.mkdir(parents=True, exist_ok=True)
(local_cache / "sub").mkdir(parents=True, exist_ok=True)
(local_cache / "sub" / "a.jpg").write_bytes(real_file.read_bytes())

composed = model.getOverlayThumbnail(model.images[0])
check("overlay renders with backfilled dimensions",
      composed is not None and not composed.isNull())
if composed is not None and not composed.isNull():
    img = composed.toImage()
    # The rectangle spans image coords (10,10)-(100,80) of a 120x90 image, so an
    # interior point must be tinted (this fails with the old `width or 1` bug).
    sx = composed.width() / 120.0
    sy = composed.height() / 90.0
    px, py = int(55 * sx), int(45 * sy)
    base = model.getThumbnail(model.images[0])
    base_color = base.toImage().pixelColor(px, py)
    over_color = img.pixelColor(px, py)
    check("overlay lands inside the thumbnail", over_color != base_color,
          (base_color.getRgb(), over_color.getRgb()))


# ------------------------------------------------------- sync to server
window.current_project_id = pid
labels_dir = cache / "labels"
labels_dir.mkdir(parents=True, exist_ok=True)
(labels_dir / "a.json").write_text('{"shapes": []}')
dbm.save_annotation(img_id, {"version": "5.4.1", "flags": {}, "shapes": [],
                             "imagePath": "../images/sub/a.jpg",
                             "imageData": None, "imageHeight": 1, "imageWidth": 1})
sftp.uploads.clear()
window.syncToServer()
check("sync uploads label file",
      any(u.endswith("labels/a.json") for u in sftp.uploads), sftp.uploads)
check("sync uploads db snapshot",
      any(u.endswith("annotation_engine.db") for u in sftp.uploads), sftp.uploads)
check("db snapshot is a sqlite file",
      sftp.files.get("/data/images/annotation_engine.db", b"")[:6] == b"SQLite")

# Local project reports it is not remote instead of uploading.
window.current_project_id = local_pid
_messages.clear()
window.syncToServer()
check("sync on local project is rejected", bool(_messages), _messages)

window.annotations_dirty = False
window.close()

print()
if failures:
    print(f"FINAL_SSH_FAILED: {failures}")
    sys.exit(1)
print("FINAL_SSH_OK")