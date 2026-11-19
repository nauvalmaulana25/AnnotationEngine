"""
AnnotationEngine Desktop - Import Labels Dialog
"""
import json
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QFileDialog, QComboBox, QCheckBox, QFormLayout,
    QMessageBox
)

from annotation_engine.core.database import (
    get_project, get_project_images, get_annotation, save_annotation,
    update_image
)


class ImportLabelsDialog(QDialog):
    """Dialog for importing LabelMe JSON annotations."""
    
    def __init__(self, parent=None, project_id=None):
        super().__init__(parent)
        
        self.project_id = project_id
        self.selected_files: List[str] = []
        self.selected_folder: Optional[str] = None
        
        self.setWindowTitle("Import Labels")
        self.setModal(True)
        self.resize(600, 400)
        
        self.setupUI()
    
    def setupUI(self):
        layout = QVBoxLayout(self)
        
        # Source selection
        source_group = QGroupBox("Source")
        source_layout = QVBoxLayout(source_group)
        
        files_btn = QPushButton("Select LabelMe JSON Files...")
        files_btn.clicked.connect(self.selectFiles)
        source_layout.addWidget(files_btn)
        
        folder_btn = QPushButton("Select Folder...")
        folder_btn.clicked.connect(self.selectFolder)
        source_layout.addWidget(folder_btn)
        
        layout.addWidget(source_group)
        
        # Options
        options_group = QGroupBox("Options")
        options_layout = QFormLayout(options_group)
        
        self.match_by = QComboBox()
        self.match_by.addItems(["Filename", "Filename (no extension)", "Image ID in JSON"])
        options_layout.addRow("Match by:", self.match_by)

        self.recursive_check = QCheckBox("Include subfolders")
        self.recursive_check.setChecked(True)
        options_layout.addRow(self.recursive_check)
        
        self.overwrite_check = QCheckBox("Overwrite existing annotations")
        options_layout.addRow(self.overwrite_check)
        
        layout.addWidget(options_group)
        
        # Buttons
        buttons = QHBoxLayout()
        buttons.addStretch()
        
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        buttons.addWidget(cancel_btn)
        
        import_btn = QPushButton("Import")
        import_btn.setDefault(True)
        import_btn.clicked.connect(self.doImport)
        buttons.addWidget(import_btn)
        
        layout.addLayout(buttons)
    
    def selectFiles(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select LabelMe JSON Files", str(Path.home()),
            "JSON Files (*.json)"
        )
        if files:
            self.selected_files = files
            self.selected_folder = None
    
    def selectFolder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select Folder", str(Path.home())
        )
        if folder:
            self.selected_folder = folder
            self.selected_files = []
    
    # ------------------------------------------------------------------
    # Import helpers
    # ------------------------------------------------------------------
    def _collect_json_files(self) -> List[Path]:
        if self.selected_files:
            return [
                Path(path) for path in self.selected_files
                if Path(path).suffix.lower() == ".json"
            ]
        if self.selected_folder:
            folder = Path(self.selected_folder)
            pattern = "**/*.json" if self.recursive_check.isChecked() else "*.json"
            return sorted(folder.glob(pattern))
        return []

    def _build_indexes(self, images: List[Dict]) -> Dict[str, Dict]:
        by_id: Dict[int, Dict] = {}
        by_name: Dict[str, List[Dict]] = {}
        by_rel: Dict[str, List[Dict]] = {}
        by_stem: Dict[str, List[Dict]] = {}

        for image in images:
            try:
                by_id[int(image['id'])] = image
            except (KeyError, TypeError, ValueError):
                pass

            name = (image.get('filename') or '').lower()
            if name:
                by_name.setdefault(name, []).append(image)
                by_stem.setdefault(Path(name).stem.lower(), []).append(image)

            rel = (image.get('relative_path') or '').replace('\\', '/').lower()
            if rel:
                by_rel.setdefault(rel, []).append(image)

        return {
            "by_id": by_id,
            "by_name": by_name,
            "by_rel": by_rel,
            "by_stem": by_stem,
        }

    @staticmethod
    def _unique(candidates: List[Dict]) -> Optional[Dict]:
        unique = {id(image): image for image in candidates or []}
        if len(unique) == 1:
            return next(iter(unique.values()))
        return None

    def _match_image(
        self, data: Dict, json_path: Path, indexes: Dict[str, Dict]
    ) -> Optional[Dict]:
        mode = self.match_by.currentText()
        image_path = str(data.get('imagePath') or '')
        ref_name = Path(image_path).name if image_path else ''
        json_name = json_path.name

        if mode == "Image ID in JSON":
            raw_id = data.get('image_id', data.get('imageId', data.get('id')))
            try:
                image = indexes["by_id"].get(int(raw_id))
            except (TypeError, ValueError):
                image = None
            if image is not None:
                return image
            # Fall through to name matching when the JSON has no usable id.

        if mode == "Filename (no extension)":
            stems = set()
            for name in (ref_name, json_name):
                if not name:
                    continue
                path = Path(name)
                stems.add(path.stem.lower())
                if path.suffix.lower() == ".json":
                    stems.add(Path(path.stem).stem.lower())
            for stem in stems:
                image = self._unique(indexes["by_stem"].get(stem, []))
                if image is not None:
                    return image

        # Exact filename / relative-path matching, also used as the fallback
        # for the image-id mode.
        for name in (ref_name, json_name):
            if not name:
                continue
            image = self._unique(indexes["by_name"].get(name.lower(), []))
            if image is not None:
                return image

        if image_path:
            rel = image_path.replace('\\', '/').lower()
            image = self._unique(indexes["by_rel"].get(rel, []))
            if image is not None:
                return image
            for rel_path, candidates in indexes["by_rel"].items():
                if rel_path.endswith('/' + rel):
                    image = self._unique(candidates)
                    if image is not None:
                        return image

        return None

    @staticmethod
    def _normalize_annotation(data: Dict, image: Dict) -> Dict:
        data.setdefault('version', '5.4.1')
        data.setdefault('flags', {})
        data['imagePath'] = image.get('filename') or data.get('imagePath') or ''
        if not data.get('imageHeight'):
            data['imageHeight'] = image.get('height') or 0
        if not data.get('imageWidth'):
            data['imageWidth'] = image.get('width') or 0
        data.setdefault('imageData', None)
        return data

    def doImport(self):
        if not self.project_id:
            return

        project = get_project(self.project_id)
        if not project:
            QMessageBox.warning(self, "Import Labels", "Project not found.")
            return

        files = self._collect_json_files()
        if not files:
            QMessageBox.warning(
                self, "Import Labels",
                "Select one or more JSON files or a folder first."
            )
            return

        base_path = Path(project['base_path'])
        labels_dir = base_path / 'labels'
        labels_dir.mkdir(parents=True, exist_ok=True)

        images = get_project_images(self.project_id)
        indexes = self._build_indexes(images)
        overwrite = self.overwrite_check.isChecked()

        imported = 0
        skipped = 0
        failed = 0
        errors: List[str] = []

        for json_path in files:
            try:
                with open(json_path, 'r', encoding='utf-8') as handle:
                    data = json.load(handle)
                if not isinstance(data, dict) or not isinstance(data.get('shapes'), list):
                    raise ValueError("not a LabelMe JSON file (missing shapes)")

                image = self._match_image(data, json_path, indexes)
                if image is None:
                    skipped += 1
                    errors.append(f"{json_path.name}: no matching image")
                    continue

                label_path = labels_dir / f"{Path(image['filename']).stem}.json"
                existing = get_annotation(image['id'])
                if (existing or label_path.exists()) and not overwrite:
                    skipped += 1
                    continue

                data = self._normalize_annotation(data, image)
                save_annotation(image['id'], data)
                update_image(image['id'], has_annotation=1)

                with open(label_path, 'w', encoding='utf-8') as handle:
                    json.dump(data, handle, indent=2)
                imported += 1
            except Exception as exc:
                failed += 1
                errors.append(f"{json_path.name}: {exc}")

        lines = [
            f"Imported: {imported}",
            f"Skipped: {skipped}",
            f"Failed: {failed}",
        ]
        if errors:
            preview = errors[:10]
            lines.append("")
            lines.extend(preview)
            if len(errors) > len(preview):
                lines.append(f"... and {len(errors) - len(preview)} more")

        QMessageBox.information(self, "Import Labels", "\n".join(lines))
        self.accept()
