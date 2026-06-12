import os
from PIL import Image

image_dir = '/tmp/kassa-app-clone2/images'

for filename in os.listdir(image_dir):
    if filename.endswith('.png') and not filename.startswith('Gemini_Generated'):
        filepath = os.path.join(image_dir, filename)
        output_filename = filename.replace('.png', '.webp')
        output_path = os.path.join(image_dir, output_filename)
        
        try:
            with Image.open(filepath) as img:
                # Resize to web-friendly size
                img.thumbnail((400, 400))
                # Save as WebP
                img.save(output_path, 'WEBP', quality=80)
                print(f"✅ Converted: {filename} -> {output_filename}")
            # Remove original PNG to save space in repo
            os.remove(filepath)
        except Exception as e:
            print(f"❌ Failed to convert {filename}: {e}")
