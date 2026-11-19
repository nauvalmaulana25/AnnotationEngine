"""
AnnotationEngine Desktop - File Operations
"""
import os
import shutil
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from PIL import Image


def get_image_info(image_path: Path) -> Dict[str, Any]:
    """Get image metadata."""
    try:
        with Image.open(image_path) as img:
            return {
                'width': img.width,
                'height': img.height,
                'format': img.format,
                'mode': img.mode,
                'file_size': image_path.stat().st_size
            }
    except Exception as e:
        return {
            'width': 0,
            'height': 0,
            'error': str(e)
        }


def create_thumbnail(image_path: Path, output_path: Path, size: tuple = (200, 200)) -> bool:
    """Create thumbnail for image."""
    try:
        with Image.open(image_path) as img:
            img.thumbnail(size, Image.LANCZOS)
            img.save(output_path)
        return True
    except Exception:
        return False


def scan_images(directory: Path, recursive: bool = True) -> List[Path]:
    """Scan directory for image files."""
    from annotation_engine.config import SUPPORTED_IMAGE_FORMATS
    
    images = []
    pattern = "**/*" if recursive else "*"
    
    for ext in SUPPORTED_IMAGE_FORMATS:
        images.extend(directory.glob(f"{pattern}{ext}"))
    
    return sorted(images)


def copy_image_to_project(
    src_path: Path,
    project_base: Path,
    images_dir_name: str = "images"
) -> Optional[Path]:
    """Copy image to project images directory."""
    images_dir = project_base / images_dir_name
    images_dir.mkdir(parents=True, exist_ok=True)
    
    dst = images_dir / src_path.name
    
    # Handle duplicates
    counter = 1
    while dst.exists():
        stem = src_path.stem
        suffix = src_path.suffix
        dst = images_dir / f"{stem}_{counter}{suffix}"
        counter += 1
    
    try:
        shutil.copy2(src_path, dst)
        return dst.relative_to(project_base)
    except Exception:
        return None


def build_labelme_payload(
    shapes: List[Dict],
    image_path: str,
    image_width: int,
    image_height: int,
    version: str = "5.4.1",
) -> Dict[str, Any]:
    """Build a LabelMe JSON document with LabelMe's exact key set.

    The key order and names mirror what LabelMe itself writes (camelCase,
    ``imageData`` last but one), so the file opens in LabelMe unchanged.
    ``image_path`` is stored as given; LabelMe resolves it relative to the
    label file, so callers pass a path relative to the ``labels`` directory.
    """
    return {
        "version": version,
        "flags": {},
        "shapes": list(shapes or []),
        "imagePath": image_path,
        "imageData": None,
        "imageHeight": image_height,
        "imageWidth": image_width,
    }


def write_labelme_json(payload: Dict, output_path: Path) -> bool:
    """Write a LabelMe JSON document atomically, matching LabelMe's indent."""
    try:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a sibling temp file first so a crash mid-write cannot leave
        # a truncated label file behind.
        tmp_path = output_path.with_name(output_path.name + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        os.replace(tmp_path, output_path)
        return True
    except Exception:
        return False


def export_labelme_json(
    shapes: List[Dict],
    image_path: Path,
    image_width: int,
    image_height: int,
    output_path: Path,
    relative_image_path: Optional[str] = None,
) -> bool:
    """Export shapes to a LabelMe JSON file."""
    payload = build_labelme_payload(
        shapes=shapes,
        image_path=relative_image_path or image_path.name,
        image_width=image_width,
        image_height=image_height,
    )
    return write_labelme_json(payload, output_path)


def import_labelme_json(json_path: Path) -> Optional[Dict]:
    """Import LabelMe JSON file."""
    try:
        with open(json_path, 'r') as f:
            return json.load(f)
    except Exception:
        return None


def match_annotations_to_images(
    label_files: List[Path],
    image_files: List[Path],
    match_by: str = "filename"
) -> Dict[Path, Path]:
    """Match label files to image files."""
    matches = {}
    
    # Build lookup
    if match_by == "filename":
        image_lookup = {f.stem: f for f in image_files}
        for label_file in label_files:
            if label_file.stem in image_lookup:
                matches[label_file] = image_lookup[label_file.stem]
    elif match_by == "filename_no_ext":
        image_lookup = {f.stem: f for f in image_files}
        for label_file in label_files:
            stem = label_file.stem
            if stem in image_lookup:
                matches[label_file] = image_lookup[stem]
    
    return matches