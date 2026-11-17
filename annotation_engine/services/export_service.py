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
    
    def export_coco(
        self,
        output_path: Path,
        include_bboxes: bool = True,
        include_polygons: bool = True,
        include_keypoints: bool = True,
        progress_callback: Optional[callable] = None
    ) -> bool:
        """
        Export annotations in COCO format.
        """
        try:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Build COCO structure
            coco = {
                'info': {
                    'description': f'{self.project["name"]} Dataset',
                    'version': '1.0',
                    'year': 2024
                },
                'licenses': [],
                'images': [],
                'annotations': [],
                'categories': []
            }
            
            # Build category mapping
            categories = self._get_category_mapping(True, True)
            for name, cat_id in sorted(categories.items(), key=lambda x: x[1]):
                coco['categories'].append({
                    'id': cat_id + 1,  # COCO uses 1-based indexing
                    'name': name,
                    'supercategory': 'object'
                })
            
            cat_name_to_coco_id = {name: cat_id + 1 for name, cat_id in categories.items()}
            
            # Process images
            annotation_id = 1
            total = len(self.images)
            
            for i, image in enumerate(self.images):
                if progress_callback:
                    progress_callback(
                        int((i / total) * 100),
                        f"Processing {image['filename']}"
                    )
                
                # Add image info
                coco_image = {
                    'id': image['id'],
                    'file_name': image['filename'],
                    'width': image['width'] or 0,
                    'height': image['height'] or 0
                }
                coco['images'].append(coco_image)
                
                # Get annotation
                annotation = get_annotation(image['id'])
                if not annotation:
                    continue
                
                img_width = image['width'] or 1
                img_height = image['height'] or 1
                
                for shape in annotation['data'].get('shapes', []):
                    label = shape.get('label', 'unknown')
                    shape_type = shape.get('shape_type', 'polygon')
                    points = shape.get('points', [])
                    
                    if label not in cat_name_to_coco_id:
                        continue
                    
                    cat_id = cat_name_to_coco_id[label]
                    
                    if shape_type == 'rectangle' and len(points) >= 2:
                        if not include_bboxes:
                            continue
                        
                        x1, y1 = points[0]
                        x2, y2 = points[1]
                        x = min(x1, x2)
                        y = min(y1, y2)
                        w = abs(x2 - x1)
                        h = abs(y2 - y1)
                        
                        coco['annotations'].append({
                            'id': annotation_id,
                            'image_id': image['id'],
                            'category_id': cat_id,
                            'bbox': [x, y, w, h],
                            'area': w * h,
                            'iscrowd': 0,
                            'segmentation': []
                        })
                        annotation_id += 1
                    
                    elif shape_type == 'polygon' and len(points) >= 3:
                        if not include_polygons:
                            continue
                        
                        # Flatten points for COCO segmentation
                        segmentation = []
                        for x, y in points:
                            segmentation.append(x)
                            segmentation.append(y)
                        
                        # Calculate bbox from polygon
                        xs = [p[0] for p in points]
                        ys = [p[1] for p in points]
                        x, y = min(xs), min(ys)
                        w, h = max(xs) - x, max(ys) - y
                        
                        # Calculate area using shoelace formula
                        area = 0
                        for j in range(len(points)):
                            x1, y1 = points[j]
                            x2, y2 = points[(j + 1) % len(points)]
                            area += x1 * y2 - x2 * y1
                        area = abs(area) / 2
                        
                        coco['annotations'].append({
                            'id': annotation_id,
                            'image_id': image['id'],
                            'category_id': cat_id,
                            'bbox': [x, y, w, h],
                            'area': area,
                            'iscrowd': 0,
                            'segmentation': [segmentation]
                        })
                        annotation_id += 1
                    
                    elif shape_type == 'point' and len(points) >= 1:
                        if not include_keypoints:
                            continue
                        
                        x, y = points[0]
                        
                        # COCO keypoint format: [x, y, visibility]
                        # visibility: 0=not labeled, 1=labeled but not visible, 2=visible
                        keypoints = [x, y, 2]
                        
                        coco['annotations'].append({
                            'id': annotation_id,
                            'image_id': image['id'],
                            'category_id': cat_id,
                            'bbox': [x - 1, y - 1, 2, 2],  # Small bbox around point
                            'area': 4,
                            'iscrowd': 0,
                            'keypoints': keypoints,
                            'num_keypoints': 1
                        })
                        annotation_id += 1
            
            # Write COCO JSON
            with open(output_path, 'w') as f:
                json.dump(coco, f, indent=2)
            
            if progress_callback:
                progress_callback(100, f"Exported {total} images to COCO format")
            
            return True
            
        except Exception as e:
            print(f"COCO export error: {e}")
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
        """Export both YOLO and COCO formats."""
        try:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            yolo_dir = output_dir / 'yolo'
            coco_path = output_dir / 'coco.json'
            
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
                progress_callback(50, "Exporting COCO format...")
            
            def coco_progress(p, msg):
                if progress_callback:
                    progress_callback(50 + p // 2, f"COCO: {msg}")
            
            coco_success = self.export_coco(
                coco_path, include_bboxes, include_polygons, include_keypoints,
                coco_progress
            )
            
            if progress_callback:
                progress_callback(100, "Export complete")
            
            return yolo_success and coco_success
            
        except Exception as e:
            print(f"Export both error: {e}")
            return False