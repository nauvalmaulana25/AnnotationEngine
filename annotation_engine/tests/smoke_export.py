"""Headless smoke test for export (split vs flat, OBB) and optional-split import."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

TMP = Path(tempfile.mkdtemp(prefix="ae_export_"))

import annotation_engine.config as config
config.DATABASE_PATH = TMP / "test.db"
config.PROJECTS_DIR = TMP / "projects"
import annotation_engine.core.database as dbm
dbm.DATABASE_PATH = config.DATABASE_PATH

from PySide6.QtGui import QPixmap, QColor
from PySide6.QtWidgets import QApplication

app = QApplication([])
failures = []


def check(name, cond, extra=""):
    if cond:
        print(f"PASS {name}")
    else:
        print(f"FAIL {name} {extra}")
        failures.append(name)


# ------------------------------------------------------- optional split import
from annotation_engine.ui.dialogs.import_images import ImportImagesDialog

dlg = ImportImagesDialog(project_id=None)
check("import combo offers None as first option",
      dlg.split_combo.itemData(0) is None, dlg.split_combo.itemData(0))
check("import combo still offers splits",
      [dlg.split_combo.itemData(i) for i in range(dlg.split_combo.count())]
      == [None, "train", "val", "test"],
      [dlg.split_combo.itemData(i) for i in range(dlg.split_combo.count())])
dlg.close()

pid = dbm.create_project("Export", TMP / "projects")
img_id = dbm.add_image(pid, "a.png", "images/a.png", 100, 100, 0, None)
row = dbm.get_image(img_id)
check("image imported without split stores None", row["split"] is None, row["split"])

# A real image on disk, and a split for the grouped-export test.
base = Path(dbm.get_project(pid)["base_path"])
(base / "images").mkdir(parents=True, exist_ok=True)
pm = QPixmap(100, 100)
pm.fill(QColor("white"))
pm.save(str(base / "images" / "a.png"))
dbm.update_image(img_id, split="train")

dbm.save_annotation(img_id, {
    "version": "5.4.1", "flags": {}, "imagePath": "../images/a.png",
    "imageData": None, "imageHeight": 100, "imageWidth": 100,
    "shapes": [
        {"label": "box", "shape_type": "rectangle",
         "points": [[10, 10], [50, 50]], "flags": {}, "group_id": None,
         "description": "", "mask": None},
        {"label": "box", "shape_type": "oriented_rectangle",
         "points": [[16, 303], [31, 287], [4, 261], [-10, 276]],
         "flags": {}, "group_id": None, "description": "", "mask": None},
        {"label": "poly", "shape_type": "polygon",
         "points": [[0, 0], [10, 0], [10, 10]], "flags": {}, "group_id": None,
         "description": "", "mask": None},
    ],
})

from annotation_engine.services.export_service import ExportService

svc = ExportService(pid)

# ------------------------------------------------------- grouped (split) export
out_split = TMP / "out_split"
ok = svc.export_yolo(out_split, use_split=True, include_obb=True)
check("grouped export succeeds", ok)
check("grouped export writes data.yaml", (out_split / "data.yaml").exists())
check("grouped export writes labels/train",
      (out_split / "labels" / "train" / "a.txt").exists())

# ------------------------------------------------------- flat export
out_flat = TMP / "out_flat"
ok = svc.export_yolo(out_flat, use_split=False, include_obb=True)
check("flat export succeeds", ok)
check("flat export has no data.yaml", not (out_flat / "data.yaml").exists())
check("flat export writes labels directly", (out_flat / "labels" / "a.txt").exists())
check("flat export has no split subfolder",
      not (out_flat / "labels" / "train").exists())

lines = (out_flat / "labels" / "a.txt").read_text().splitlines()
check("flat export has a rectangle line",
      any(len(line.split()) == 5 for line in lines), lines)
check("flat export has a polygon (seg) line",
      any(len(line.split()) == 7 for line in lines), lines)

obb_lines = [line for line in lines if len(line.split()) == 9]
check("flat export has an oriented-box line", len(obb_lines) == 1, lines)
if obb_lines:
    tokens = obb_lines[0].split()
    check("obb line keeps raw (negative) corner",
          float(tokens[-2]) == -0.1, tokens)  # -10 / 100 = -0.1

# OBB excluded when the checkbox is off.
out_noobb = TMP / "out_noobb"
ok = svc.export_yolo(out_noobb, use_split=False, include_obb=False)
check("obb-disabled export succeeds", ok)
lines_noobb = (out_noobb / "labels" / "a.txt").read_text().splitlines()
check("obb-disabled drops oriented-box line",
      not any(len(line.split()) == 9 for line in lines_noobb), lines_noobb)


# ------------------------------------------------------- split distribution
import yaml as _yaml

pid2 = dbm.create_project("Dist", TMP / "projects")
base2 = Path(dbm.get_project(pid2)["base_path"])
(base2 / "images").mkdir(parents=True, exist_ok=True)
for i in range(10):
    p = base2 / "images" / f"{i}.png"
    pm = QPixmap(10, 10)
    pm.fill(QColor("white"))
    pm.save(str(p))
    # Imported without a split (None).
    dbm.add_image(pid2, f"{i}.png", f"images/{i}.png", 10, 10, 0, None)

svc2 = ExportService(pid2)
out_dist = TMP / "out_dist"
ok = svc2.export_yolo(
    out_dist, use_split=True,
    split_distribution={"train": 0.5, "val": 0.5, "test": 0.0},
)
check("distribution export succeeds", ok)

data = _yaml.safe_load((out_dist / "data.yaml").read_text())
check("data.yaml lists train", "train" in data, data)
check("data.yaml lists val", "val" in data, data)
check("data.yaml omits test when 0%", "test" not in data, data)

train_count = len(list((out_dist / "labels" / "train").glob("*.txt")))
val_count = len(list((out_dist / "labels" / "val").glob("*.txt")))
check("unassigned images distributed across train/val",
      train_count > 0 and val_count > 0 and train_count + val_count == 10,
      (train_count, val_count))
check("no test folder when test is 0%",
      not (out_dist / "labels" / "test").exists())

# Assignment stays deterministic across runs (same result re-exported).
ok2 = svc2.export_yolo(
    TMP / "out_dist2", use_split=True,
    split_distribution={"train": 0.5, "val": 0.5, "test": 0.0},
)
check("distribution is deterministic",
      train_count == len(list((TMP / "out_dist2" / "labels" / "train").glob("*.txt")))
      and val_count == len(list((TMP / "out_dist2" / "labels" / "val").glob("*.txt"))))

print()
if failures:
    print(f"FINAL_EXPORT_FAILED: {failures}")
    sys.exit(1)
print("FINAL_EXPORT_OK")
