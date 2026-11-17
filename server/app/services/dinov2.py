import torch
import numpy as np
from PIL import Image
from typing import List, Dict, Tuple, Optional
from collections import defaultdict
import math

from transformers import AutoImageProcessor, AutoModel


class DINOv2KeypointService:
    def __init__(self, model_name: str = "facebook/dinov2-small", device: str = None):
        if device is None:
            device = "cuda" if torch.cuda.is_available() else "cpu"
        self.device = device
        self.model_name = model_name
        self.processor = AutoImageProcessor.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name).to(device)
        self.model.eval()
    
    def extract_features(self, image: Image.Image) -> Tuple[np.ndarray, Tuple[float, float]]:
        """Extract dense patch features from image."""
        inputs = self.processor(images=image, return_tensors="pt").to(self.device)
        with torch.no_grad():
            outputs = self.model(**inputs)
        
        # last_hidden_state: [1, num_patches + 1, D] (includes CLS token)
        patch_tokens = outputs.last_hidden_state[:, 1:, :]  # remove CLS
        
        # Reshape to spatial grid
        h_patches = int((inputs.pixel_values.shape[2] // 14))
        w_patches = int((inputs.pixel_values.shape[3] // 14))
        feature_map = patch_tokens.reshape(1, h_patches, w_patches, -1).squeeze(0)
        
        # Scale factors: original pixel per patch
        scale = (image.height / (h_patches * 14), image.width / (w_patches * 14))
        
        return feature_map.cpu().numpy(), scale
    
    def match_keypoints(
        self,
        ref_feature_map: np.ndarray,
        ref_keypoints: List[Tuple[float, float, str]],
        target_feature_map: np.ndarray,
        ref_scale: Tuple[float, float],
        target_scale: Tuple[float, float],
        similarity_threshold: float = 0.4
    ) -> List[Dict]:
        """
        Match reference keypoints to target image using cosine similarity.
        
        Args:
            ref_feature_map: [H_ref, W_ref, D]
            ref_keypoints: list of (x, y, label) in original image pixels
            target_feature_map: [H_tgt, W_tgt, D]
            ref_scale: (scale_y, scale_x) for reference
            target_scale: (scale_y, scale_x) for target
            similarity_threshold: minimum cosine similarity
            
        Returns:
            List of matched keypoints: [{x, y, label, score}, ...]
        """
        H_ref, W_ref, D = ref_feature_map.shape
        H_tgt, W_tgt, _ = target_feature_map.shape
        
        # Normalize feature maps for cosine similarity
        ref_norm = ref_feature_map / (np.linalg.norm(ref_feature_map, axis=2, keepdims=True) + 1e-8)
        tgt_norm = target_feature_map / (np.linalg.norm(target_feature_map, axis=2, keepdims=True) + 1e-8)
        
        matched = []
        for x, y, label in ref_keypoints:
            # Map reference pixel to patch coordinates
            px = int(x / (ref_scale[1] * 14))
            py = int(y / (ref_scale[0] * 14))
            px = np.clip(px, 0, W_ref - 1)
            py = np.clip(py, 0, H_ref - 1)
            
            # Get query vector
            query_vec = ref_norm[py, px]  # [D]
            
            # Compute cosine similarity across all target patches
            sims = (tgt_norm.reshape(-1, D) @ query_vec).reshape(H_tgt, W_tgt)
            
            # Find best match
            best_idx = np.unravel_index(np.argmax(sims), sims.shape)
            best_score = sims[best_idx]
            
            if best_score >= similarity_threshold:
                # Map patch back to pixel coordinates
                tx = (best_idx[1] + 0.5) * target_scale[1] * 14
                ty = (best_idx[0] + 0.5) * target_scale[0] * 14
                matched.append({
                    "x": float(tx),
                    "y": float(ty),
                    "label": label,
                    "score": float(best_score)
                })
            else:
                # Occluded or not found
                matched.append({
                    "x": None,
                    "y": None,
                    "label": label,
                    "score": float(best_score)
                })
        
        return matched
    
    def consensus_filter(
        self,
        all_matched: List[Dict],
        min_votes: int = 2
    ) -> List[Dict]:
        """
        Filter keypoints requiring consensus across reference images.
        
        Args:
            all_matched: List of matched keypoints from all references
            min_votes: Minimum number of references that must agree
            
        Returns:
            Filtered keypoints with averaged positions
        """
        by_label = defaultdict(list)
        for kp in all_matched:
            if kp["x"] is not None and kp["y"] is not None:
                by_label[kp["label"]].append(kp)
        
        consensus = []
        for label, matches in by_label.items():
            if len(matches) < min_votes:
                continue
            
            # Average position, max confidence
            avg_x = sum(m["x"] for m in matches) / len(matches)
            avg_y = sum(m["y"] for m in matches) / len(matches)
            max_score = max(m["score"] for m in matches)
            
            consensus.append({
                "x": avg_x,
                "y": avg_y,
                "label": label,
                "score": max_score
            })
        
        return consensus
    
    def per_label_nms(
        self,
        keypoints: List[Dict],
        img_w: int,
        img_h: int,
        dist_pct: float = 0.025
    ) -> List[Dict]:
        """
        Per-label Non-Maximum Suppression to remove spatial duplicates.
        """
        diag = math.hypot(img_w, img_h)
        dist_thresh = diag * dist_pct
        
        by_label = defaultdict(list)
        for kp in keypoints:
            by_label[kp["label"]].append(kp)
        
        final = []
        for label, group in by_label.items():
            # Sort by confidence descending
            group.sort(key=lambda m: m["score"], reverse=True)
            
            kept = []
            for kp in group:
                x, y = kp["x"], kp["y"]
                too_close = any(
                    math.hypot(x - k["x"], y - k["y"]) < dist_thresh
                    for k in kept
                )
                if not too_close:
                    kept.append(kp)
            
            final.extend(kept)
        
        return final
    
    def transfer_keypoints(
        self,
        target_image_path: str,
        ref_data_list: List[Dict],
        similarity_threshold: float = 0.4,
        consensus_votes: int = 2,
        nms_dist_pct: float = 0.025
    ) -> List[Dict]:
        """
        Transfer keypoints from reference images to target image.
        
        Args:
            target_image_path: Path to target image
            ref_data_list: List of dicts with 'image_path' and 'keypoints' [(x, y, label), ...]
            similarity_threshold: Cosine similarity threshold
            consensus_votes: Minimum references for consensus
            nms_dist_pct: NMS distance as % of image diagonal
            
        Returns:
            List of transferred keypoints: [{x, y, label, score}, ...]
        """
        # Load target image
        target_img = Image.open(target_image_path).convert("RGB")
        orig_w, orig_h = target_img.size
        
        # Extract target features
        tgt_feat, tgt_scale = self.extract_features(target_img)
        
        # Match against each reference
        all_matched = []
        for ref_data in ref_data_list:
            ref_img = Image.open(ref_data["image_path"]).convert("RGB")
            ref_feat, ref_scale = self.extract_features(ref_img)
            
            matched = self.match_keypoints(
                ref_feat, ref_data["keypoints"], tgt_feat,
                ref_scale, tgt_scale, similarity_threshold
            )
            all_matched.extend(matched)
        
        # Consensus filtering
        consensus = self.consensus_filter(all_matched, consensus_votes)
        
        # Per-label NMS
        final = self.per_label_nms(consensus, orig_w, orig_h, nms_dist_pct)
        
        return final