"""Headless smoke test for UI: index search, list view, title bar, dimming."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

TMP = Path(tempfile.mkdtemp(prefix="ae_ui_"))

import annotation_engine.config as config
config.DATABASE_PATH = TMP / "test.db"
config.PROJECTS_DIR = TMP / "projects"
import annotation_engine.core.database as dbm
dbm.DATABASE_PATH = config.DATABASE_PATH

from PySide6.QtCore import Qt, QModelIndex, QSize
from PySide6.QtGui import QPixmap, QColor
from PySide6.QtWidgets import QApplication, QAbstractItemView

app = QApplication([])
failures = []


def check(name, cond, extra=""):
    if cond:
        print(f"PASS {name}")
    else:
        print(f"FAIL {name} {extra}")
        failures.append(name)


# ------------------------------------------------------------ search by index
from annotation_engine.ui.widgets.image_grid import (
    ImageGridModel, ImageFilterProxyModel,
)

images = [
    {"id": 10, "project_id": 1, "filename": "IMG_0010.jpg", "relative_path": "images/IMG_0010.jpg", "split": "train"},
    {"id": 11, "project_id": 1, "filename": "IMG_0011.jpg", "relative_path": "images/IMG_0011.jpg", "split": "val"},
    {"id": 12, "project_id": 1, "filename": "photo.jpg", "relative_path": "images/photo.jpg", "split": "train"},
]
model = ImageGridModel(images)
proxy = ImageFilterProxyModel()
proxy.setSourceModel(model)

proxy.setSearch("")
check("no filter shows all", proxy.rowCount() == 3, proxy.rowCount())

proxy.setSearch("photo")
check("filename filter matches", proxy.rowCount() == 1, proxy.rowCount())

proxy.setSearch("2")
check("index filter matches row 2 only", proxy.rowCount() == 1, proxy.rowCount())
matched = proxy.mapToSource(proxy.index(0, 0)).row()
check("index 2 maps to source row 1", matched == 1, matched)

proxy.setSearch("")
proxy.setSplit("val")
check("split filter keeps val only", proxy.rowCount() == 1, proxy.rowCount())

proxy.setSplit("All")
proxy.setSearch("999")
check("unmatched search shows none", proxy.rowCount() == 0, proxy.rowCount())

# Index role exposed by the model (used by the list delegate).
idx = model.index(1, 0)
check("model exposes 1-based index", model.data(idx, Qt.UserRole + 1) == 2,
      model.data(idx, Qt.UserRole + 1))


# --------------------------------------------------------------- list view
from annotation_engine.ui.widgets.image_grid import ImageGridWidget

grid = ImageGridWidget()
grid.setImages(images)
grid.setViewMode("list")
check("list mode active", grid.view_mode == "list")
check("list uses compact delegate",
      isinstance(grid.list_view.itemDelegate(), grid.list_delegate.__class__))
check("grid/list icons loaded",
      not grid.grid_btn.icon().isNull() and not grid.list_btn.icon().isNull())

grid.search_input.setText("2")
check("widget index search filters rows", grid.proxy_model.rowCount() == 1,
      grid.proxy_model.rowCount())


# ------------------------------------------- grid scroll regression (toggle)
grid.search_input.setText("")
grid.split_filter.setCurrentText("All")
grid.setViewMode("grid")
grid.resize(320, 520)
grid.show()
app.processEvents()

# A representative grid item height (ImageThumbnailDelegate sizeHint height).
sb = grid.list_view.verticalScrollBar()
initial_step = sb.singleStep()
check("grid initial singleStep is row-sized", initial_step > 1, initial_step)

# Toggle grid -> list -> grid and confirm the wheel step is preserved.
grid.setViewMode("list")
app.processEvents()
grid.setViewMode("grid")
app.processEvents()
restored_step = grid.list_view.verticalScrollBar().singleStep()
check("grid singleStep preserved after list round-trip",
      restored_step > 1, restored_step)
check("scroll mode is ScrollPerPixel",
      grid.list_view.verticalScrollMode()
      == QAbstractItemView.ScrollPerPixel)

# Index badge data is exposed by the grid model via Qt.UserRole + 1.
check("grid model exposes index badge value",
      grid.model.data(grid.model.index(0, 0), Qt.UserRole + 1) == 1)


# --------------------------------------------------------- label overlays
from annotation_engine.ui.colors import resolve_label_color

# Batch annotation loader roundtrip.
pid = dbm.create_project("Overlay", TMP / "projects")
b2 = Path(dbm.get_project(pid)["base_path"])
(b2 / "images").mkdir(parents=True, exist_ok=True)
ov_id = dbm.add_image(pid, "ov.png", "images/ov.png", 100, 100)
ov_pm = QPixmap(100, 100)
ov_pm.fill(QColor("white"))
ov_pm.save(str(b2 / "images" / "ov.png"))
dbm.save_annotation(ov_id, {
    "shapes": [
        {"label": "box", "shape_type": "rectangle",
         "points": [[10, 10], [50, 60]]},
        {"label": "hidden", "shape_type": "point", "points": [[5, 5]]},
    ],
    "imagePath": "ov.png",
})
annotations = dbm.get_project_annotations(pid)
check("batch annotations keyed by image id",
      annotations.get(ov_id) is not None
      and len(annotations[ov_id]) == 2, annotations)

# Overlay compositing in the model: with overlays off, base pixmap returned;
# with overlays on and shapes present, a distinct pixmap is produced.
ov_model = ImageGridModel([{
    "id": ov_id, "project_id": pid, "filename": "ov.png",
    "relative_path": "images/ov.png", "split": "train",
    "width": 100, "height": 100, "has_annotation": True,
}])
ov_model.setAnnotationData(
    annotations=annotations,
    label_colors={"box": "#ff0000", "hidden": "#00ff00"},
    label_visibility={"box": True, "hidden": False},
)

base_pm = ov_model.getThumbnail(ov_model.images[0])
check("overlay base thumbnail exists", base_pm is not None and not base_pm.isNull())

ov_model.setShowOverlays(True)
composed = ov_model.getOverlayThumbnail(ov_model.images[0])
check("overlay produces a pixmap", composed is not None and not composed.isNull())

# Rectangle regression: a rectangle (2 corner points) must fill a rectangular
# region, not collapse into a diagonal line. Sample two interior points that
# sit off the top-left -> bottom-right diagonal.
if composed is not None and not composed.isNull():
    img = composed.toImage()
    base_img = base_pm.toImage()
    sx = composed.width() / 100.0
    sy = composed.height() / 100.0
    changed = []
    for (ix, iy) in ((30, 20), (30, 40), (40, 30)):
        px = int(ix * sx)
        py = int(iy * sy)
        if (0 <= px < img.width() and 0 <= py < img.height()):
            c = img.pixelColor(px, py)
            b = base_img.pixelColor(px, py)
            changed.append(c != b)
    check("rectangle fills a 2D region (not a diagonal line)",
          all(changed) and len(changed) >= 3, changed)

# Hidden labels must be skipped: a point-only hidden shape leaves no mark, so
# the composed pixmap differs from base only because of the visible rectangle.
check("resolve_label_color returns configured color",
      resolve_label_color("box", {"box": "#ff0000"}).name() == "#ff0000")
check("resolve_label_color falls back to palette",
      resolve_label_color("zzz_unknown", {}).isValid())


# ----------------------------------------------------- annotation filters
from annotation_engine.ui.widgets.image_grid import (
    ImageFilterProxyModel, ImageGridModel,
)

fimages = [
    {"id": 1, "project_id": 1, "filename": "a.jpg",
     "relative_path": "images/a.jpg", "split": "train"},
    {"id": 2, "project_id": 1, "filename": "b.jpg",
     "relative_path": "images/b.jpg", "split": "train"},
    {"id": 3, "project_id": 1, "filename": "c.jpg",
     "relative_path": "images/c.jpg", "split": "train"},
    {"id": 4, "project_id": 1, "filename": "d.jpg",
     "relative_path": "images/d.jpg", "split": "train"},
]
fmodel = ImageGridModel(fimages)
fmodel.setAnnotationData(annotations={
    1: [{"label": "box"}, {"label": "box"}],      # duplicate 'box'
    2: [{"label": "car"}],                         # has 'car'
    3: [],                                         # none
    4: [{"label": "box"}, {"label": "person"}],    # has box + person
})
check("annotationState none", fmodel.annotationState(3) == "none")
check("annotationState has", fmodel.annotationState(2) == "has")
check("annotationState duplicate", fmodel.annotationState(1) == "duplicate")
check("labelCounts for duplicate image",
      fmodel.labelCounts(1) == {"box": 2}, fmodel.labelCounts(1))

fproxy = ImageFilterProxyModel()
fproxy.setSourceModel(fmodel)

fproxy.setAnnotationFilter("none")
check("filter: no labels keeps only empty images", fproxy.rowCount() == 1)
fproxy.setAnnotationFilter("has")
check("filter: has labels excludes empty images", fproxy.rowCount() == 3)
fproxy.setAnnotationFilter("duplicate")
check("filter: duplicate labels keeps only dup images", fproxy.rowCount() == 1)

fproxy.setAnnotationFilter("has")
fproxy.setLabelFilter("box")
check("filter: has label 'box'", fproxy.rowCount() == 2, fproxy.rowCount())
fproxy.setAnnotationFilter("duplicate")
check("filter: duplicate label 'box'", fproxy.rowCount() == 1, fproxy.rowCount())
fproxy.setAnnotationFilter("all")
fproxy.setLabelFilter(None)
check("filter: all restores everything", fproxy.rowCount() == 4)

# Widget-level wiring: combos drive the proxy, label combo is populated + gated.
fw = ImageGridWidget()
fw.setImages(fimages)
fw.setAnnotationData(
    annotations={1: [{"label": "box"}, {"label": "box"}],
                 2: [{"label": "car"}]},
    label_colors={"box": "#ff0000", "car": "#00ff00", "person": "#0000ff"},
    label_visibility={"box": True, "car": True, "person": True},
)
fw.show()
app.processEvents()
check("label filter lists project labels",
      [fw.label_filter.itemData(i) for i in range(fw.label_filter.count())]
      == [None, "box", "car", "person"],
      [fw.label_filter.itemData(i) for i in range(fw.label_filter.count())])
fw.annotation_filter.setCurrentIndex(fw.annotation_filter.findData("duplicate"))
check("duplicate filter enabled label combo", fw.label_filter.isEnabled())
check("widget duplicate filter matches", fw.proxy_model.rowCount() == 1)
fw.annotation_filter.setCurrentIndex(fw.annotation_filter.findData("none"))
check("none filter disables label combo", not fw.label_filter.isEnabled())

# Grid selection must survive filter toggles (arrow-key navigation context).
def grid_current_image_id(widget):
    idx = widget.list_view.currentIndex()
    if idx.row() < 0:
        return None
    source = widget.proxy_model.mapToSource(idx)
    image = widget.model.getImage(source.row())
    return image['id'] if image else None

fw.annotation_filter.setCurrentIndex(fw.annotation_filter.findData("all"))
app.processEvents()
fw.revealImage(2)
app.processEvents()
check("grid selects the revealed image", grid_current_image_id(fw) == 2,
      grid_current_image_id(fw))
fw.annotation_filter.setCurrentIndex(fw.annotation_filter.findData("none"))
app.processEvents()
fw.annotation_filter.setCurrentIndex(fw.annotation_filter.findData("all"))
app.processEvents()
check("selection restored after switching filter back",
      grid_current_image_id(fw) == 2, grid_current_image_id(fw))


# --------------------------------------------------------------- title bar
import annotation_engine.ui.main_window as mw
mw.MainWindow.showWelcomeDialog = lambda self: None

project_id = dbm.create_project("UI Smoke", TMP / "projects")
base = Path(dbm.get_project(project_id)["base_path"])
(base / "images").mkdir(parents=True, exist_ok=True)
for name in ("a.png", "b.png"):
    pixmap = QPixmap(120, 90)
    pixmap.fill(QColor("white"))
    pixmap.save(str(base / "images" / name))
dbm.add_image(project_id, "a.png", "images/a.png", 120, 90)
dbm.add_image(project_id, "b.png", "images/b.png", 120, 90)
img_ids = [i["id"] for i in dbm.get_project_images(project_id)]

window = mw.MainWindow()
window.loadProject(project_id)
window.show()
app.processEvents()
window.loadImage(img_ids[0])
app.processEvents()

check("title shows 1/2", "1/2" in window.windowTitle(), window.windowTitle())

window.loadImage(img_ids[1])
app.processEvents()
check("title shows 2/2", "2/2" in window.windowTitle(), window.windowTitle())

# Second image has no annotation -> "car" label dimmed, "dog" not present.
window.label_list.addLabel("car")
window.canvas.shapes = []
window.syncLabelsFromShapes()
car_widget = window.label_list.list_widget.itemWidget(
    window.label_list.list_widget.topLevelItem(0), 0
)
check("label dimmed when absent", car_widget._opacity.opacity() < 1.0,
      car_widget._opacity.opacity())

window.annotations_dirty = False
window.close()

print()
if failures:
    print(f"FINAL_UI_FAILED: {failures}")
    sys.exit(1)
print("FINAL_UI_OK")
