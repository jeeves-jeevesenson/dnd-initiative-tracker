#!/usr/bin/env python3
"""
Create Windows icon file from PNG images
"""
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("ERROR: Pillow is required. Install it with: pip install Pillow")
    sys.exit(1)


def create_icon(output_path: Path, *png_paths: Path):
    """
    Create a Windows .ico file from one or more PNG images
    
    Args:
        output_path: Path to save the .ico file
        png_paths: Paths to PNG images (multiple sizes recommended)
    """
    images = []
    
    for png_path in png_paths:
        if not png_path.exists():
            print(f"Warning: {png_path} not found, skipping")
            continue
        
        try:
            img = Image.open(png_path)
            # Convert to RGBA if needed
            if img.mode != 'RGBA':
                img = img.convert('RGBA')
            images.append(img)
            print(f"Loaded {png_path} ({img.size[0]}x{img.size[1]})")
        except Exception as e:
            print(f"Error loading {png_path}: {e}")
    
    if not images:
        print("ERROR: No valid PNG images found")
        sys.exit(1)
    
    # Save as .ico with multiple sizes
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        images[0].save(
            output_path,
            format='ICO',
            sizes=[(img.size[0], img.size[1]) for img in images]
        )
        print(f"\nSuccessfully created icon: {output_path}")
        print(f"Icon contains {len(images)} size(s)")
    except Exception as e:
        print(f"ERROR: Failed to create icon: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Get the repository root (parent of scripts directory)
    script_dir = Path(__file__).parent
    repo_dir = script_dir.parent
    assets_dir = repo_dir / "assets"
    
    # Input PNG files (use different sizes for better icon quality)
    png_192 = assets_dir / "graphic-192.png"
    png_512 = assets_dir / "graphic-512.png"
    
    # Output icon file
    icon_path = assets_dir / "icon.ico"
    
    print("Creating Windows icon from PNG images...")
    print(f"Output: {icon_path}")
    print()
    
    create_icon(icon_path, png_192, png_512)
