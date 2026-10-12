"""Create original app icon and preserve bundled dependencies' license notices."""
from pathlib import Path
import importlib.metadata as metadata
import shutil
import sys
from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent


def main():
    image = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((3, 3, 253, 253), radius=58, fill='#0D2934')
    draw.pieslice((44, 24, 212, 192), start=35, end=145, fill='#1FB7AD')
    draw.arc((61, 40, 195, 174), start=37, end=143, fill='#8DE6D8', width=9)
    draw.line([(39, 190), (74, 190), (93, 165), (114, 211), (139, 153), (158, 190), (217, 190)], fill='#F0FBF8', width=10, joint='curve')
    image.save(HERE / 'sonocopilot.ico', format='ICO', sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
    image.save(HERE / 'sonocopilot.png')
    dependencies = ['numpy','Pillow','pydicom','pylibjpeg','pylibjpeg-libjpeg','pylibjpeg-openjpeg',
                    'PySide6','PySide6_Essentials','PySide6_Addons','PySide6_WebEngine',
                    'PySide6_Pdf','shiboken6','reportlab','charset-normalizer']
    for name in dependencies:
        distribution = metadata.distribution(name)
        dest = HERE / 'licenses' / f'{distribution.metadata["Name"]}-{distribution.version}'
        dest.mkdir(parents=True, exist_ok=True)
        for file in distribution.files or []:
            if any(word in file.name.lower() for word in ('license','licence','copying','notice')):
                source = Path(distribution.locate_file(file))
                if source.is_file():
                    target = dest / str(file).replace('/', '__').replace('\\', '__')
                    shutil.copy2(source, target)
        info = f'Name: {distribution.metadata["Name"]}\nVersion: {distribution.version}\nLicense: {distribution.metadata.get("License-Expression", distribution.metadata.get("License", "See bundled notices"))}\n'
        (dest / 'PACKAGE.txt').write_text(info, encoding='utf-8')
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if python_license.exists():
        shutil.copy2(python_license, HERE / 'licenses' / 'Python-LICENSE.txt')


if __name__ == '__main__':
    main()
