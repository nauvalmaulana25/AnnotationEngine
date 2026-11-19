"""
AnnotationEngine Desktop - Export Service
"""
import os
import json
import yaml
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional
from collections import defaultdict

from annotation_engine.core.database import (
    get_database, get_project, get_project_images, get_annotation
)
from annotation_engine.config import EXPORT_FORMATS
from annotation_engine.utils.file_ops import build_labelme_payload, write_labelme_json


class ExportService:
    """Export annotations to YOLO and COCO formats."""
    
    def __init__(self, project_id: int):
        self.project_id = project_id
        self.project = get_project(project_id)
        if not self.project:
            raise ValueError(f"Project {project_id} not found")
        
        self.base_path = Path(self.project['base_path'])
        self.images = get_project_images(project_id)
        self.image_map = {img['id']: img for img in self.images}
    
    def _get_category_mapping(self, include_polygons: bool, include_keypoints: bool) -> Dict:
        """Build category mapping from all annotations."""
        categories = {}
        cat_id = 0
        
        for image in self.images:
            annotation = get_annotation(image['id'])
            if not annotation:
                continue
            
            for shape in annotation['data'].get('shapes', []):
                label = shape.get('label', 'unknown')
                shape_type = shape.get('shape_type', 'polygon')
                
                # Determine if this shape type should be included
                include = False
                if shape_type == 'rectangle' and True:  # bboxes always included
                    include = True
                elif shape_type == 'polygon' and include_polygons:
                    include = True
                elif shape_type == 'point' and include_keypoints:
                    include = True
                
                if include and label not in categories:
                    categories[label] = cat_id
                    cat_id += 1
        
        return categories
    
    def export_yolo(
        self,
        output_dir: Path,
        split_ratios: Dict[str, float],
        include_bboxes: bool = True,
        include_polygons: bool = True,
        include_keypoints: bool = True,
        progress_callback: Optional[callable] = None
    ) -> bool:
        """
        Export annotations in YOLO format.
        
        YOLO format: one .txt file per image with lines:
        class_id x_center y_center width height [keypoint_x keypoint_y visibility ...]
        """
        try:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Create split directories
            for split in ['train', 'val', 'test']:
                (output_dir / 'images' / split).mkdir(parents=True, exist_ok=True)
                (output_dir / 'labels' / split).mkdir(parents=True, exist_ok=True)
            
            # Get category mapping
            categories = self._get_category_mapping(True, True)
            
            # Write data.yaml
            data_yaml = {
                'path': str(output_dir.absolute()),
                'train': 'images/train',
                'val': 'images/val',
                'test': 'images/test',
                'nc': len(categories),
                'names': [name for name, _ in sorted(categories.items(), key=lambda x: x[1])]
            }
            
            with open(output_dir / 'data.yaml', 'w') as f:
                yaml.dump(data_yaml, f, default_flow_style=False)
            
            # Process images
            total = len(self.images)
            for i, image in enumerate(self.images):
                if progress_callback:
                    progress_callback(
                        int((i / total) * 100),
                        f"Exporting {image['filename']}"
                    )
                
                # Determine split
                split = image.get('split', 'train')
                if split not in ['train', 'val', 'test']:
                    split = 'train'
                
                # Copy image
                src = self.base_path / image['relative_path']
                dst = output_dir / 'images' / split / image['filename']
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                
                # Get annotation
                annotation = get_annotation(image['id'])
                if not annotation:
                    # Create empty label file
                    label_file = output_dir / 'labels' / split / f"{Path(image['filename']).stem}.txt"
                    label_file.touch()
                    continue
                
                # Convert shapes to YOLO format
                yolo_lines = []
                img_width = image['width'] or 1
                img_height = image['height'] or 1
                
                for shape in annotation['data'].get('shapes', []):
                    label = shape.get('label', 'unknown')
                    shape_type = shape.get('shape_type', 'polygon')
                    points = shape.get('points', [])
                    
                    if label not in categories:
                        continue
                    
                    cat_id = categories[label]
                    
                    if shape_type == 'rectangle' and len(points) >= 2:
                        # Bounding box
                        x1, y1 = points[0]
                        x2, y2 = points[1]
                        x_center = (x1 + x2) / 2 / img_width
                        y_center = (y1 + y2) / 2 / img_height
                        width = abs(x2 - x1) / img_width
                        height = abs(y2 - y1) / img_height
                        
                        yolo_lines.append(f"{cat_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}")
                    
                    elif shape_type == 'polygon' and len(points) >= 3:
                        # Polygon (YOLO seg format)
                        normalized = []
                        for x, y in points:
                            normalized.append(f"{x / img_width:.6f}")
                            normalized.append(f"{y / img_height:.6f}")
                        
                        if include_polygons:
                            yolo_lines.append(f"{cat_id} " + " ".join(normalized))
                    
                    elif shape_type == 'point' and len(points) >= 1:
                        # Keypoint
                        if include_keypoints:
                            x, y = points[0]
                            # YOLO keypoint format: class_id x_center y_center width height kp_x kp_y visibility
                            # For keypoints only, we use a minimal bbox
                            x_center = x / img_width
                            y_center = y / img_height
                            kp_x = x / img_width
                            kp_y = y / img_height
                            visibility = 2  # visible
                            
                            # Need a bbox for keypoints - use small box around point
                            box_size = 0.01
                            yolo_lines.append(
                                f"{cat_id} {x_center:.6f} {y_center:.6f} {box_size:.6f} {box_size:.6f} "
                                f"{kp_x:.6f} {kp_y:.6f} {visibility}"
                            )
                
                # Write label file
                label_file = output_dir / 'labels' / split / f"{Path(image['filename']).stem}.txt"
                with open(label_file, 'w') as f:
                    f.write('\n'.join(yolo_lines))
            
            if progress_callback:
                progress_callback(100, f"Exported {total} images to YOLO format")
            
            return True
            
        except Exception as e:
            print(f"YOLO export error: {e}")
            return False
    
    def export_labelme(
        self,
        output_dir: Path,
        copy_images: bool = True,
        progress_callback: Optional[callable] = None
    ) -> bool:
        """Export annotations as standard LabelMe JSON files.

        The layout mirrors a LabelMe folder so the result opens directly in
        LabelMe::

            <output_dir>/labels/<stem>.json
            <output_dir>/images/<name>        (when copy_images is on)

        Every shape is written verbatim, so circles, LineStrips, masks and
        other non-rectangle kinds survive the round trip.
        """
        try:
            output_dir = Path(output_dir)
            labels_dir = output_dir / 'labels'
            images_dir = output_dir / 'images'
            labels_dir.mkdir(parents=True, exist_ok=True)
            if copy_images:
                images_dir.mkdir(parents=True, exist_ok=True)

            total = len(self.images)
            for i, image in enumerate(self.images):
                if progress_callback:
                    progress_callback(
                        int((i / total) * 100),
                        f"Exporting {image['filename']}"
                    )

                if copy_images:
                    src = self.base_path / image['relative_path']
                    dst = images_dir / image['filename']
                    if src.exists():
                        shutil.copy2(src, dst)

                annotation = get_annotation(image['id'])
                shapes = annotation['data'].get('shapes', []) if annotation else []

                relative = (image.get('relative_path') or image['filename']).replace('\\', '/')
                payload = build_labelme_payload(
                    shapes=shapes,
                    image_path=f"../{relative}" if copy_images else relative,
                    image_width=image['width'] or 0,
                    image_height=image['height'] or 0,
                )
                write_labelme_json(
                    payload,
                    labels_dir / f"{Path(image['filename']).stem}.json"
                )

            if progress_callback:
                progress_callback(100, f"Exported {total} images to LabelMe format")

            return True

        except Exception as e:
            print(f"LabelMe export error: {e}")
            return False

    def export_both(
        self,
        output_dir: Path,
        split_ratios: Dict[str, float],
        include_bboxes: bool = True,
        include_polygons: bool = True,
        include_keypoints: bool = True,
        progress_callback: Optional[callable] = None
    ) -> bool:
        """Export both YOLO and LabelMe formats."""
        try:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            yolo_dir = output_dir / 'yolo'
            labelme_dir = output_dir / 'labelme'
            
            if progress_callback:
                progress_callback(0, "Exporting YOLO format...")
            
            def yolo_progress(p, msg):
                if progress_callback:
                    progress_callback(p // 2, f"YOLO: {msg}")
            
            yolo_success = self.export_yolo(
                yolo_dir, split_ratios, include_bboxes, include_polygons, include_keypoints,
                yolo_progress
            )
            
            if progress_callback:
                progress_callback(50, "Exporting LabelMe format...")
            
            def labelme_progress(p, msg):
                if progress_callback:
                    progress_callback(50 + p // 2, f"LabelMe: {msg}")
            
            labelme_success = self.export_labelme(
                labelme_dir, copy_images=True, progress_callback=labelme_progress
            )
            
            if progress_callback:
                progress_callback(100, "Export complete")
            
            return yolo_success and labelme_success
            
        except Exception as e:
            print(f"Export both error: {e}")
            return False