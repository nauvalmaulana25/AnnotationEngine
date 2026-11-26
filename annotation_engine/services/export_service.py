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
    
    def __init__(self, project_id: int, image_resolver=None):
        self.project_id = project_id
        self.project = get_project(project_id)
        if not self.project:
            raise ValueError(f"Project {project_id} not found")
        
        self.base_path = Path(self.project['base_path'])
        self.images = get_project_images(project_id)
        self.image_map = {img['id']: img for img in self.images}
        # Optional callback(image) -> local path, used for SSH projects whose
        # images are only cached on demand.
        self.image_resolver = image_resolver
        self.skipped_images = 0

    def _resolveImageSource(self, image: dict) -> Optional[Path]:
        """Return a local path for an image, fetching it on demand if needed."""
        local = self.base_path / image['relative_path']
        if local.exists():
            return local
        if self.image_resolver is not None:
            try:
                resolved = self.image_resolver(image)
            except Exception:
                resolved = None
            if resolved and Path(resolved).exists():
                return Path(resolved)
        return None
    
    def _get_category_mapping(self, include_polygons: bool, include_keypoints: bool,
                              include_obb: bool) -> Dict:
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
                elif shape_type == 'oriented_rectangle' and include_obb:
                    include = True
                elif shape_type == 'polygon' and include_polygons:
                    include = True
                elif shape_type == 'point' and include_keypoints:
                    include = True
                
                if include and label not in categories:
                    categories[label] = cat_id
                    cat_id += 1
        
        return categories
    
    def _assignSplits(
        self, split_distribution: Optional[Dict[str, float]] = None
    ) -> Dict[int, str]:
        """Map each image id to a split for a grouped export.

        Images that already carry a ``train``/``val``/``test`` split keep it.
        Images without one are distributed by the relative weights of
        ``split_distribution`` (normalized; a zero test weight yields no test
        split). The assignment is deterministic because ``self.images`` is
        already ordered by import time.
        """
        assigned: Dict[int, str] = {}
        unassigned = []
        for image in self.images:
            split = image.get('split')
            if split in ('train', 'val', 'test'):
                assigned[image['id']] = split
            else:
                unassigned.append(image)

        if not unassigned:
            return assigned

        distribution = split_distribution or {}
        weights = {
            'train': float(distribution.get('train', 0.7) or 0),
            'val': float(distribution.get('val', 0.2) or 0),
            'test': float(distribution.get('test', 0.1) or 0),
        }
        total = sum(weights.values())
        if total <= 0:
            total = 1.0
            weights['train'] = 1.0

        # Cumulative thresholds; a split with zero weight shares its threshold
        # with the previous one, so it naturally receives no images.
        thresholds: Dict[str, float] = {}
        running = 0.0
        for split in ('train', 'val', 'test'):
            running += weights[split] / total
            thresholds[split] = running

        n = len(unassigned)
        for i, image in enumerate(unassigned):
            pos = (i + 0.5) / n
            if pos < thresholds['train']:
                assigned[image['id']] = 'train'
            elif pos < thresholds['val']:
                assigned[image['id']] = 'val'
            else:
                assigned[image['id']] = 'test'

        return assigned
    
    def export_yolo(
        self,
        output_dir: Path,
        use_split: bool = True,
        split_distribution: Optional[Dict[str, float]] = None,
        include_bboxes: bool = True,
        include_obb: bool = True,
        include_polygons: bool = True,
        include_keypoints: bool = True,
        progress_callback: Optional[callable] = None,
        output_root_override: Optional[str] = None
    ) -> bool:
        """
        Export annotations in YOLO format.
        
        YOLO format: one .txt file per image with lines:
        class_id x_center y_center width height [keypoint_x keypoint_y visibility ...]
        
        With ``use_split`` the images/labels are grouped into train/val/test
        subfolders and a ``data.yaml`` is written; otherwise the layout is flat
        (``images/`` and ``labels/``) and no ``data.yaml`` is generated.

        ``split_distribution`` (train/val/test relative weights) assigns images
        that were imported without a split; images that already carry a split
        keep it. A zero test weight means no test split is produced.
        """
        try:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            
            images_root = output_dir / 'images'
            labels_root = output_dir / 'labels'
            
            # Precompute each image's split (only meaningful when grouping).
            split_by_id: Dict[int, str] = {}
            if use_split:
                split_by_id = self._assignSplits(split_distribution)
                used_splits = sorted(set(split_by_id.values()))
                for split in used_splits:
                    (images_root / split).mkdir(parents=True, exist_ok=True)
                    (labels_root / split).mkdir(parents=True, exist_ok=True)
            else:
                images_root.mkdir(parents=True, exist_ok=True)
                labels_root.mkdir(parents=True, exist_ok=True)
            
            # Get category mapping
            categories = self._get_category_mapping(
                include_polygons, include_keypoints, include_obb
            )
            
            # Write data.yaml (only when grouping by split), listing only the
            # splits that actually receive images.
            if use_split:
                data_yaml = {
                    'path': output_root_override or str(output_dir.absolute())
                }
                for split in ('train', 'val', 'test'):
                    if split in split_by_id.values():
                        data_yaml[split] = f'images/{split}'
                data_yaml['nc'] = len(categories)
                data_yaml['names'] = [
                    name for name, _ in sorted(categories.items(), key=lambda x: x[1])
                ]
                
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
                
                # Determine destination folders
                if use_split:
                    split = split_by_id.get(image['id'], 'train')
                    img_dst_dir = images_root / split
                    lbl_dst_dir = labels_root / split
                else:
                    img_dst_dir = images_root
                    lbl_dst_dir = labels_root
                
                # Copy image
                src = self._resolveImageSource(image)
                if src is None:
                    # Remote image that could not be fetched: skip rather than
                    # abort the whole export.
                    self.skipped_images += 1
                    continue
                dst = img_dst_dir / image['filename']
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                
                # Get annotation
                annotation = get_annotation(image['id'])
                if not annotation:
                    # Create empty label file
                    label_file = lbl_dst_dir / f"{Path(image['filename']).stem}.txt"
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
                    
                    elif shape_type == 'oriented_rectangle' and len(points) >= 4:
                        # Oriented bounding box: class_id + 4 normalized corners.
                        if include_obb:
                            corners = []
                            for x, y in points[:4]:
                                corners.append(f"{x / img_width:.6f}")
                                corners.append(f"{y / img_height:.6f}")
                            yolo_lines.append(f"{cat_id} " + " ".join(corners))
                    
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
                label_file = lbl_dst_dir / f"{Path(image['filename']).stem}.txt"
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
                    src = self._resolveImageSource(image)
                    dst = images_dir / image['filename']
                    if src is not None:
                        shutil.copy2(src, dst)
                    else:
                        self.skipped_images += 1

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
        use_split: bool = True,
        include_bboxes: bool = True,
        include_obb: bool = True,
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
                yolo_dir, use_split=use_split, include_bboxes=include_bboxes,
                include_obb=include_obb, include_polygons=include_polygons,
                include_keypoints=include_keypoints, progress_callback=yolo_progress,
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