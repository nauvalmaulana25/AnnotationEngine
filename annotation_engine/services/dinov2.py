"""
AnnotationEngine Desktop - DINOv2 Keypoint Service
"""
import os
import torch
import torch.nn.functional as F
from PIL import Image
from transformers import AutoImageProcessor, AutoModel
from typing import List, Dict, Any, Optional, Callable, Tuple
from pathlib import Path
import numpy as np

from annotation_engine.services.device import DEVICE_AUTO, torch_device


class DINOv2KeypointService:
    """DINOv2-based zero-shot keypoint transfer."""
    
    def __init__(self, model_name: str = "facebook/dinov2-small",
                 device: str = DEVICE_AUTO):
        """
        Initialize DINOv2 keypoint service.
        
        Args:
            model_name: Hugging Face model name (dinov2-small, dinov2-base, dinov2-large, dinov2-giant)
            device: Inference device preference (``auto``, ``cpu``, ``cuda:0``…)
        """
        self.model_name = model_name
        self.device_preference = device
        self.device = torch_device(device)
        
        print(f"Loading DINOv2 model: {model_name} on {self.device}")
        
        self.processor = AutoImageProcessor.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name).to(self.device)
        self.model.eval()
        
        # Patch size for DINOv2
        self.patch_size = 14
        
        print(f"DINOv2 loaded successfully")
    
    @torch.no_grad()
    def extract_features(self, image: Image.Image) -> Tuple[torch.Tensor, Tuple[int, int]]:
        """
        Extract DINOv2 features from image.
        
        Returns:
            (features, (height, width)) where features shape is [1, num_patches+1, hidden_dim]
        """
        # Prepare image
        inputs = self.processor(images=image, return_tensors="pt").to(self.device)
        
        # Get model outputs
        outputs = self.model(**inputs)
        
        # last_hidden_state: [1, num_patches+1, hidden_dim]
        # First token is CLS, rest are patch tokens
        features = outputs.last_hidden_state
        
        # Get original image size
        width, height = image.size
        
        return features, (height, width)
    
    def _get_patch_grid(self, height: int, width: int) -> Tuple[int, int]:
        """Calculate patch grid size."""
        h_patches = height // self.patch_size
        w_patches = width // self.patch_size
        return h_patches, w_patches
    
    def _keypoint_to_patch(self, keypoint: Dict, h_patches: int, w_patches: int, 
                          height: int, width: int) -> Tuple[int, int]:
        """Convert keypoint coordinates to patch indices."""
        x, y = keypoint['x'], keypoint['y']
        
        # Normalize to [0, 1]
        norm_x = x / width
        norm_y = y / height
        
        # Convert to patch indices
        patch_x = int(norm_x * w_patches)
        patch_y = int(norm_y * h_patches)
        
        # Clamp
        patch_x = max(0, min(patch_x, w_patches - 1))
        patch_y = max(0, min(patch_y, h_patches - 1))
        
        return patch_y, patch_x  # (row, col)
    
    def _patch_to_keypoint(self, patch_y: int, patch_x: int, 
                          h_patches: int, w_patches: int,
                          height: int, width: int) -> Tuple[float, float]:
        """Convert patch indices back to keypoint coordinates."""
        # Center of patch
        norm_x = (patch_x + 0.5) / w_patches
        norm_y = (patch_y + 0.5) / h_patches
        
        x = norm_x * width
        y = norm_y * height
        
        return x, y
    
    @torch.no_grad()
    def match_keypoints(
        self,
        target_features: torch.Tensor,
        target_size: Tuple[int, int],
        reference_features: torch.Tensor,
        reference_size: Tuple[int, int],
        reference_keypoints: List[Dict],
        similarity_threshold: float = 0.4
    ) -> List[Dict]:
        """
        Match keypoints from reference to target using cosine similarity.
        
        Args:
            target_features: Target image features [1, N+1, D]
            target_size: (height, width) of target image
            reference_features: Reference image features [1, M+1, D]
            reference_size: (height, width) of reference image
            reference_keypoints: List of keypoints in reference image
            similarity_threshold: Minimum cosine similarity
            
        Returns:
            List of matched keypoints in target image coordinates
        """
        # Remove CLS token (first token)
        target_patches = target_features[0, 1:, :]  # [N, D]
        reference_patches = reference_features[0, 1:, :]  # [M, D]
        
        # Normalize for cosine similarity
        target_norm = F.normalize(target_patches, p=2, dim=1)
        reference_norm = F.normalize(reference_patches, p=2, dim=1)
        
        # Compute similarity matrix: [M, N]
        similarity = torch.mm(reference_norm, target_norm.t())
        
        # Get patch grid sizes
        target_h, target_w = target_size
        ref_h, ref_w = reference_size
        target_h_patches, target_w_patches = self._get_patch_grid(target_h, target_w)
        ref_h_patches, ref_w_patches = self._get_patch_grid(ref_h, ref_w)
        
        matched_keypoints = []
        
        for kp in reference_keypoints:
            # Convert keypoint to reference patch index
            ref_patch_y, ref_patch_x = self._keypoint_to_patch(
                kp, ref_h_patches, ref_w_patches, ref_h, ref_w
            )
            ref_patch_idx = ref_patch_y * ref_w_patches + ref_patch_x
            
            # Get similarity scores for this reference patch
            scores = similarity[ref_patch_idx]  # [N]
            
            # Find best match above threshold
            max_score, best_idx = scores.max(dim=0)
            
            if max_score.item() >= similarity_threshold:
                # Convert target patch index to coordinates
                target_patch_y = best_idx.item() // target_w_patches
                target_patch_x = best_idx.item() % target_w_patches
                
                x, y = self._patch_to_keypoint(
                    target_patch_y, target_patch_x,
                    target_h_patches, target_w_patches,
                    target_size[0], target_size[1]
                )
                
                matched_keypoints.append({
                    'x': x,
                    'y': y,
                    'label': kp.get('label', 'keypoint'),
                    'score': max_score.item(),
                    'reference_label': kp.get('label', 'keypoint')
                })
        
        return matched_keypoints
    
    def transfer_keypoints(
        self,
        target_image_path: str,
        reference_data: List[Dict],
        similarity_threshold: float = 0.4,
        consensus_votes: int = 2,
        nms_distance: float = 0.05,
        progress_callback: Optional[Callable[[int, str], None]] = None
    ) -> List[Dict]:
        """
        Transfer keypoints from multiple reference images to target.
        
        Args:
            target_image_path: Path to target image
            reference_data: List of dicts with 'image_path' and 'keypoints'
            similarity_threshold: Minimum cosine similarity for matches
            consensus_votes: Minimum number of references agreeing on a keypoint
            nms_distance: NMS distance as fraction of image diagonal
            progress_callback: Optional progress callback
            
        Returns:
            List of consensus keypoints
        """
        if progress_callback:
            progress_callback(10, "Loading target image...")
        
        # Load target image
        target_image = Image.open(target_image_path).convert('RGB')
        target_features, target_size = self.extract_features(target_image)
        
        if progress_callback:
            progress_callback(30, "Loading reference images...")
        
        # Process each reference
        all_matches = []
        total_refs = len(reference_data)
        
        for i, ref in enumerate(reference_data):
            if progress_callback:
                progress_callback(
                    30 + int((i / total_refs) * 50),
                    f"Processing reference {i+1}/{total_refs}"
                )
            
            ref_image = Image.open(ref['image_path']).convert('RGB')
            ref_features, ref_size = self.extract_features(ref_image)
            
            matches = self.match_keypoints(
                target_features, target_size,
                ref_features, ref_size,
                ref['keypoints'],
                similarity_threshold
            )
            
            # Add reference index to matches
            for match in matches:
                match['reference_idx'] = i
            
            all_matches.extend(matches)
        
        if progress_callback:
            progress_callback(80, "Applying consensus filtering...")
        
        # Consensus filtering: group by label and position
        consensus_keypoints = self._consensus_filter(
            all_matches, target_image.size, consensus_votes, nms_distance
        )
        
        if progress_callback:
            progress_callback(100, f"Found {len(consensus_keypoints)} consensus keypoints")
        
        return consensus_keypoints
    
    def _consensus_filter(
        self,
        matches: List[Dict],
        image_size: Tuple[int, int],
        min_votes: int,
        nms_distance: float
    ) -> List[Dict]:
        """Apply consensus filtering and NMS to matches."""
        if not matches:
            return []
        
        width, height = image_size
        diagonal = (width**2 + height**2)**0.5
        nms_threshold = nms_distance * diagonal
        
        # Group by label
        from collections import defaultdict
        label_groups = defaultdict(list)
        for match in matches:
            label_groups[match['label']].append(match)
        
        consensus_keypoints = []
        
        for label, group in label_groups.items():
            if len(group) < min_votes:
                continue
            
            # Cluster by position (simple clustering)
            clusters = []
            for match in group:
                x, y = match['x'], match['y']
                assigned = False
                
                for cluster in clusters:
                    cx, cy = cluster['center']
                    if (x - cx)**2 + (y - cy)**2 < nms_threshold**2:
                        cluster['points'].append((x, y))
                        cluster['scores'].append(match['score'])
                        cluster['refs'].append(match['reference_idx'])
                        assigned = True
                        break
                
                if not assigned:
                    clusters.append({
                        'center': (x, y),
                        'points': [(x, y)],
                        'scores': [match['score']],
                        'refs': [match['reference_idx']]
                    })
            
            # Keep clusters with enough votes
            for cluster in clusters:
                if len(cluster['points']) >= min_votes:
                    # Average position
                    avg_x = sum(p[0] for p in cluster['points']) / len(cluster['points'])
                    avg_y = sum(p[1] for p in cluster['points']) / len(cluster['points'])
                    avg_score = sum(cluster['scores']) / len(cluster['scores'])
                    
                    consensus_keypoints.append({
                        'x': avg_x,
                        'y': avg_y,
                        'label': label,
                        'score': avg_score,
                        'votes': len(cluster['points']),
                        'references': list(set(cluster['refs']))
                    })
        
        return consensus_keypoints
    
    def keypoints_to_labelme(self, keypoints: List[Dict], image_width: int, image_height: int) -> List[Dict]:
        """Convert keypoints to LabelMe format."""
        shapes = []
        for i, kp in enumerate(keypoints):
            shapes.append({
                'label': kp.get('label', f'keypoint_{i}'),
                'points': [[kp['x'], kp['y']]],
                'group_id': None,
                'description': '',
                'shape_type': 'point',
                'flags': {},
                'mask': None
            })
        return shapes