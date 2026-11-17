"""
AnnotationEngine Desktop - MobileSAM ONNX Export Script
"""
import torch
import os
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

def export_mobile_sam_to_onnx(
    checkpoint_path: str,
    output_path: str,
    model_type: str = "vit_t"
):
    """
    Export MobileSAM to ONNX format.
    
    Args:
        checkpoint_path: Path to MobileSAM checkpoint (.pth)
        output_path: Output ONNX file path
        model_type: Model type (vit_t, vit_s, vit_b, vit_l)
    """
    try:
        from mobile_sam import sam_model_registry, SamPredictor
    except ImportError:
        print("mobile_sam not installed. Install with: pip install git+https://github.com/ChaoningZhang/MobileSAM.git")
        return False
    
    print(f"Loading MobileSAM {model_type} from {checkpoint_path}")
    
    # Load model
    sam = sam_model_registry[model_type](checkpoint=checkpoint_path)
    sam.eval()
    
    # Create dummy input
    dummy_image = torch.randn(1, 3, 1024, 1024)
    
    # Export image encoder
    print("Exporting image encoder...")
    encoder_output = f"{output_path}_encoder.onnx"
    torch.onnx.export(
        sam.image_encoder,
        dummy_image,
        encoder_output,
        export_params=True,
        opset_version=11,
        do_constant_folding=True,
        input_names=['image'],
        output_names=['image_embeddings'],
        dynamic_axes={
            'image': {0: 'batch_size'},
            'image_embeddings': {0: 'batch_size'}
        }
    )
    print(f"Encoder exported to {encoder_output}")
    
    # For the decoder, we need to export prompt encoder + mask decoder
    # This is more complex and requires custom wrapper
    print("Note: Decoder export requires custom implementation based on prompt types")
    print("For now, use the full PyTorch model or export decoder separately")
    
    return True


def download_mobile_sam_checkpoint(model_type: str = "vit_t", output_dir: str = "models") -> str:
    """Download MobileSAM checkpoint from Hugging Face."""
    import requests
    from tqdm import tqdm
    
    urls = {
        "vit_t": "https://github.com/ChaoningZhang/MobileSAM/raw/master/weights/mobile_sam.pt",
    }
    
    if model_type not in urls:
        raise ValueError(f"Unknown model type: {model_type}")
    
    output_path = Path(output_dir) / f"mobile_sam_{model_type}.pt"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    if output_path.exists():
        print(f"Checkpoint already exists at {output_path}")
        return str(output_path)
    
    url = urls[model_type]
    print(f"Downloading {model_type} checkpoint from {url}")
    
    response = requests.get(url, stream=True)
    response.raise_for_status()
    
    total_size = int(response.headers.get('content-length', 0))
    
    with open(output_path, 'wb') as f:
        with tqdm(total=total_size, unit='B', unit_scale=True, desc="Downloading") as pbar:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
                    pbar.update(len(chunk))
    
    print(f"Downloaded to {output_path}")
    return str(output_path)


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Export MobileSAM to ONNX")
    parser.add_argument("--checkpoint", type=str, help="Path to MobileSAM checkpoint")
    parser.add_argument("--output", type=str, default="models/mobile_sam.onnx", help="Output ONNX path")
    parser.add_argument("--model-type", type=str, default="vit_t", choices=["vit_t", "vit_s", "vit_b", "vit_l"])
    parser.add_argument("--download", action="store_true", help="Download checkpoint if not exists")
    
    args = parser.parse_args()
    
    if args.download:
        checkpoint_path = download_mobile_sam_checkpoint(args.model_type)
    else:
        checkpoint_path = args.checkpoint
    
    if not checkpoint_path or not os.path.exists(checkpoint_path):
        print("Checkpoint not found. Use --download to download automatically.")
        sys.exit(1)
    
    success = export_mobile_sam_to_onnx(checkpoint_path, args.output, args.model_type)
    sys.exit(0 if success else 1)