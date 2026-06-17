import os
from PIL import Image

image_dir = '/Users/admin/Documents/Omnom&SweetMe/images'
output_dir = '/Users/admin/Documents/Omnom&SweetMe/images'

# Маппинг русских названий в английские (согласно index.html)
mapping = {
    'брауни.ico': 'brownie.webp',
    'грибочки.ico': 'gribochki.webp',
    'ириски.ico': 'iriska.webp',
    'ириски_асорти.ico': 'assorti.webp',
    'картошка.ico': 'kartoshka.webp',
    'колбаса.ico': 'kolbasa.webp',
    'орешки.ico': 'oreshek.webp',
    'рогалики.ico': 'rogaliki.webp',
    'трубочки.ico': 'trubochki.webp',
    'трубочки_сгуха.ico': 'trubochki_sguha.webp', # Maybe just trubochki or default?
}

for filename in os.listdir(image_dir):
    if filename.endswith('.ico'):
        filepath = os.path.join(image_dir, filename)
        output_filename = mapping.get(filename, filename.replace('.ico', '.webp'))
        output_path = os.path.join(output_dir, output_filename)
        
        try:
            with Image.open(filepath) as img:
                # RGB required for some operations, but WEBP supports RGBA
                img = img.convert("RGBA")
                # Resize to a web-friendly size (e.g., 400x400)
                img.thumbnail((400, 400))
                # Save as WebP
                img.save(output_path, 'WEBP', quality=80)
                print(f"✅ Converted: {filename} -> {output_filename}")
        except Exception as e:
            print(f"❌ Failed to convert {filename}: {e}")
