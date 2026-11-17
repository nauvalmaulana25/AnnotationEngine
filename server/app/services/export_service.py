import os
import json
import zipfile
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Callable, Awaitable
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.database import async_session_maker
from app.models import Project, Image, Annotation


class ExportService:
    def __init__(self):
        self.class_names = []
        self.class_to_id = {}
    
    async def export(
        self,
        project_id: int,
        format: str,
        split_ratios: Optional[Dict[str, float]] = None,
        include_bboxes: bool = True,
        include_polygons: bool = True,
        include_keypoints: bool = True,
        progress_callback: Optional[Callable[[int, int, str], Awaitable[None]]] = None
    ) -> str:
        """
        Export annotations in YOLO and/or COCO format.
        
        Returns path to output zip file.
        """
        async with async_session_maker() as db:
            # Load project with images and annotations
            result = await db.execute(
                select(Project)
                .options(selectinload(Project.images).selectinload(Image.annotation))
                .where(Project.id == project_id)
            )
            project = result.scalar_one_or_none()
            
            if not project:
                raise ValueError("Project not found")
            
            # Collect all unique labels
            self._collect_classes(project)
            
            # Determine splits
            if split_ratios:
                # Assign splits based on ratios
                self._assign_splits(project.images, split_ratios)
            else:
                # Use existing splits
                pass
            
            # Create output directory
            output_dir = Path(project.base_path) / "exports" / f"export_{project_id}"
            output_dir.mkdir(parents=True, exist_ok=True)
            
            if format in ("yolo", "both"):
                await self._export_yolo(project, output_dir, include_bboxes, include_polygons, include_keypoints, progress_callback)
            
            if format in ("coco", "both"):
                await self._export_coco(project, output_dir, include_bboxes, include_polygons, include_keypoints, progress_callback)
            
            # Create zip
            zip_path = output_dir.with_suffix(".zip")
            await self._create_zip(output_dir, zip_path)
            
            return str(zip_path)
    
    def _collect_classes(self, project: Project):
        """Collect all unique class labels from annotations."""
        labels = set()
        for image in project.images:
            if image.annotation:
                import json
                try:
                    data = json.loads(image.annotation.data)
                    for shape in data.get("shapes", []):
                        labels.add(shape.get("label", ""))
                except Exception:
                    pass
        
        self.class_names = sorted(list(labels))
        self.class_to_id = {name: i for i, name in enumerate(self.class_names)}
    
    def _assign_splits(self, images: List[Image], ratios: Dict[str, float]):
        """Assign train/val/test splits based on ratios."""
        import random
        random.seed(42)
        shuffled = list(images)
        random.shuffle(shuffled)
        
        total = len(shuffled)
        train_end = int(total * ratios.get("train", 0.7))
        val_end = train_end + int(total * ratios.get("val", 0.2))
        
        for i, img in enumerate(shuffled):
            if i < train_end:
                img.split = "train"
            elif i < val_end:
                img.split = "val"
            else:
                img.split = "test"
    
    async def _export_yolo(
        self,
        project: Project,
        output_dir: Path,
        include_bboxes: bool,
        include_polygons: bool,
        include_keypoints: bool,
        progress_callback: Optional[Callable] = None
    ):
        """Export in YOLO format."""
        # Create directory structure
        for split in ["train", "val", "test"]:
            (output_dir / "yolo" / split / "images").mkdir(parents=True, exist_ok=True)
            (output_dir / "yolo" / split / "labels").mkdir(parents=True, exist_ok=True)
        
        # Write data.yaml
        yaml_content = f"""path: .
train: train/images
val: val/images
test: test/images

nc: {len(self.class_names)}
names: {self.class_names}
"""
        (output_dir / "yolo" / "data.yaml").write_text(yaml_content)
        
        total = len(project.images)
        for i, image in enumerate(project.images):
            if progress_callback:
                await progress_callback(i + 1, total, f"Exporting {image.filename}")
            
            # Copy image to split folder
            split = image.split or "train"
            dst_img = output_dir / "yolo" / split / "images" / image.filename
            shutil.copy2(image.original_path, dst_img)
            
            # Create label file
            label_file = output_dir / "yolo" / split / "labels" / (Path(image.filename).stem + ".txt")
            
            lines = []
            if image.annotation:
                import json
                try:
                    data = json.loads(image.annotation.data)
                    img_w = data.get("imageWidth", image.width or 1)
                    img_h = data.get("imageHeight", image.height or 1)
                    
                    for shape in data.get("shapes", []):
                        label = shape.get("label", "")
                        if label not in self.class_to_id:
                            continue
                        class_id = self.class_to_id[label]
                        shape_type = shape.get("shape_type", "")
                        points = shape.get("points", [])
                        
                        if shape_type == "rectangle" and include_bboxes and len(points) >= 2:
                            # Convert rectangle to YOLO format
                            x1, y1 = points[0]
                            x2, y2 = points[1]
                            x_center = (x1 + x2) / 2 / img_w
                            y_center = (y1 + y2) / 2 / img_h
                            width = abs(x2 - x1) / img_w
                            height = abs(y2 - y1) / img_h
                            lines.append(f"{class_id} {x_center:.6f} {y_center:.6f} {width:.6f} {height:.6f}")
                        
                        elif shape_type == "polygon" and include_polygons and len(points) >= 3:
                            # Convert polygon to YOLO format (segmentation)
                            coords = []
                            for px, py in points:
                                coords.append(f"{px / img_w:.6f}")
                                coords.append(f"{py / img_h:.6f}")
                            lines.append(f"{class_id} " + " ".join(coords))
                        
                        elif shape_type == "point" and include_keypoints and len(points) >= 1:
                            # Convert keypoint to YOLO format (x, y, visibility)
                            px, py = points[0]
                            # YOLO keypoint: x y v (v=2 for visible)
                            lines.append(f"{class_id} {px / img_w:.6f} {py / img_h:.6f} 2")
                
                except Exception as e:
                    print(f"Error processing annotation for {image.filename}: {e}")
            
            label_file.write_text("\n".join(lines))
    
    async def _export_coco(
        self,
        project: Project,
        output_dir: Path,
        include_bboxes: bool,
        include_polygons: bool,
        include_keypoints: bool,
        progress_callback: Optional[Callable] = None
    ):
        """Export in COCO format."""
        coco_dir = output_dir / "coco"
        coco_dir.mkdir(parents=True, exist_ok=True)
        
        # COCO structure
        coco_data = {
            "images": [],
            "annotations": [],
            "categories": []
        }
        
        # Categories
        for i, name in enumerate(self.class_names):
            coco_data["categories"].append({
                "id": i,
                "name": name,
                "supercategory": "object"
            })
        
        annotation_id = 1
        total = len(project.images)
        
        for i, image in enumerate(project.images):
            if progress_callback:
                await progress_callback(i + 1, total, f"Exporting {image.filename}")
            
            # Copy image
            split = image.split or "train"
            split_dir = coco_dir / split
            split_dir.mkdir(exist_ok=True)
            dst_img = split_dir / image.filename
            shutil.copy2(image.original_path, dst_img)
            
            # Image info
            img_w = image.width
            img_h = image.height
            if not img_w or not img_h:
                from PIL import Image as PILImage
                with PILImage.open(image.original_path) as pil_img:
                    img_w, img_h = pil_img.size
            
            image_info = {
                "id": image.id,
                "file_name": f"{split}/{image.filename}",
                "width": img_w,
                "height": img_h
            }
            coco_data["images"].append(image_info)
            
            # Annotations
            if image.annotation:
                import json
                try:
                    data = json.loads(image.annotation.data)
                    
                    for shape in data.get("shapes", []):
                        label = shape.get("label", "")
                        if label not in self.class_to_id:
                            continue
                        category_id = self.class_to_id[label]
                        shape_type = shape.get("shape_type", "")
                        points = shape.get("points", [])
                        
                        if shape_type == "rectangle" and include_bboxes and len(points) >= 2:
                            x1, y1 = points[0]
                            x2, y2 = points[1]
                            x = min(x1, x2)
                            y = min(y1, y2)
                            w = abs(x2 - x1)
                            h = abs(y2 - y1)
                            
                            coco_data["annotations"].append({
                                "id": annotation_id,
                                "image_id": image.id,
                                "category_id": category_id,
                                "bbox": [x, y, w, h],
                                "area": w * h,
                                "iscrowd": 0,
                                "segmentation": []
                            })
                            annotation_id += 1
                        
                        elif shape_type == "polygon" and include_polygons and len(points) >= 3:
                            # Flatten polygon points
                            segmentation = []
                            for px, py in points:
                                segmentation.append(px)
                                segmentation.append(py)
                            
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
                            
                            coco_data["annotations"].append({
                                "id": annotation_id,
                                "image_id": image.id,
                                "category_id": category_id,
                                "bbox": [x, y, w, h],
                                "area": area,
                                "iscrowd": 0,
                                "segmentation": [segmentation]
                            })
                            annotation_id += 1
                        
                        elif shape_type == "point" and include_keypoints and len(points) >= 1:
                            # COCO keypoints format: [x, y, v] for each keypoint
                            px, py = points[0]
                            keypoints = [px, py, 2]  # v=2 visible
                            
                            coco_data["annotations"].append({
                                "id": annotation_id,
                                "image_id": image.id,
                                "category_id": category_id,
                                "bbox": [px, py, 1, 1],  # minimal bbox
                                "area": 1,
                                "iscrowd": 0,
                                "keypoints": keypoints,
                                "num_keypoints": 1
                            })
                            annotation_id += 1
                
                except Exception as e:
                    print(f"Error processing annotation for {image.filename}: {e}")
        
        # Write COCO JSON for each split
        for split in ["train", "val", "test"]:
            split_images = [img for img in coco_data["images"] if img["file_name"].startswith(f"{split}/")]
            split_image_ids = {img["id"] for img in split_images}
            split_annotations = [ann for ann in coco_data["annotations"] if ann["image_id"] in split_image_ids]
            
            split_data = {
                "images": split_images,
                "annotations": split_annotations,
                "categories": coco_data["categories"]
            }
            
            (coco_dir / f"{split}.json").write_text(json.dumps(split_data, indent=2))
        
        # Also write combined
        (coco_dir / "all.json").write_text(json.dumps(coco_data, indent=2))
    
    async def _create_zip(self, source_dir: Path, zip_path: Path):
        """Create zip archive of export directory."""
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for file_path in source_dir.rglob("*"):
                if file_path.is_file():
                    arcname = file_path.relative_to(source_dir)
                    zf.write(file_path, arcname)