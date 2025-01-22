from PIL import Image
import os
import uuid

def crop_image(image_path, output_dir):
    img = Image.open(image_path)
    cropped = img.crop((0, 0, 430, 350))  # 左上角长430高350像素
    cropped_output = os.path.join(output_dir, f"{uuid.uuid4()}.png")
    cropped.save(cropped_output)
    return cropped_output
