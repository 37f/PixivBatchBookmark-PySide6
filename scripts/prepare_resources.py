"""Convert supplied assets without altering either original image."""

from pathlib import Path
import shutil

from PIL import Image, ImageOps


def main():
    root = Path(__file__).resolve().parents[1] / 'resources'
    background = root / 'originals' / 'background.png'
    icon = root / 'originals' / 'icon.jpg'
    shutil.copyfile(background, root / 'background.png')
    with Image.open(icon) as source:
        image = ImageOps.exif_transpose(source).convert('RGBA')
        # Preserve the complete square picture, including its original background.
        canvas = Image.new('RGBA', (512, 512), (255, 255, 255, 255))
        resized = ImageOps.contain(image, (512, 512), Image.Resampling.LANCZOS)
        canvas.alpha_composite(resized, ((512 - resized.width) // 2, (512 - resized.height) // 2))
        canvas.save(root / 'icon.png')
        canvas.save(root / 'icon.ico', sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print('Prepared background.png, icon.png and multi-size icon.ico')


if __name__ == '__main__':
    main()
