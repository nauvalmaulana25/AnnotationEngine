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


def export_labelme_json(
    shapes: List[Dict],
    image_path: Path,
    image_width: int,
    image_height: int,
    output_path: Path
) -> bool:
    """Export shapes to LabelMe JSON format."""
    try:
        data = {
            "version": "5.4.1",
            "flags": {},
            "shapes": shapes,
            "imagePath": image_path.name,
            "imageData": None,
            "imageHeight": image_height,
            "imageWidth": image_width
        }
        
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception:
        return False


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