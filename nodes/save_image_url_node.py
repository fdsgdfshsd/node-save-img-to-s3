import io
import json
import numpy as np
import torch
from PIL import Image, PngImagePlugin
import boto3
from botocore.client import Config
import hashlib

class SaveImageToS3:
    def __init__(self):
        self.type = "output"
        self.compress_level = 4

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "images": ("IMAGE", {"tooltip": "Изображения для отправки."}),
                "s3_endpoint": ("STRING", {"tooltip": "S3 Endpoint URL, например: https://s3.amazonaws.com или иной."}),
                "s3_bucket": ("STRING", {"tooltip": "Имя S3 Bucket."}),
                "s3_access_key": ("STRING", {"tooltip": "Access key для S3."}),
                "s3_secret_key": ("STRING", {"tooltip": "Secret key для S3."}),
                "s3_region": ("STRING", {"default": "us-east-1", "tooltip": "Регион S3."}),
                "folder": ("STRING", {"default": "ddcn_results", "tooltip": "Папка (на сервере), куда сохранять изображение."}),
                "filename": ("STRING", {"default": "ComfyUI.png", "tooltip": "Имя файла для загружаемого изображения."})
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO"
            },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    OUTPUT_NODE = True
    FUNCTION = "save_images"
    CATEGORY = "image"
    DESCRIPTION = (
        "Отправляет входные изображения напрямую на S3 с использованием boto3. "
        "Параметры S3 (s3_endpoint, s3_bucket, s3_access_key, s3_secret_key, s3_region), folder и filename задаются через интерфейс. "
        "Возвращает первое изображение для дальнейшей цепочки."
    )

    def save_images(self, images, s3_endpoint, s3_bucket, s3_access_key, s3_secret_key, s3_region="us-east-1",
                    folder="ddcn_results", filename="ComfyUI.png", prompt=None, extra_pnginfo=None):
        results = []
        # Создаем S3-клиент с конфигурацией, аналогичной рабочему примеру
        s3_client = boto3.client(
            's3',
            endpoint_url=s3_endpoint,
            aws_access_key_id=s3_access_key,
            aws_secret_access_key=s3_secret_key,
            region_name=s3_region,
            config=Config(s3={'addressing_style': 'path'})
        )

        for batch_number, image in enumerate(images):
            # Преобразуем тензор в numpy-массив
            arr = 255.0 * image.cpu().numpy()
            arr = np.clip(arr, 0, 255).astype(np.uint8)
            # Если изображение имеет форму (C,H,W), транспонируем в (H,W,C)
            if arr.ndim == 3 and arr.shape[0] in [1, 3, 4]:
                arr = np.transpose(arr, (1, 2, 0))
            # Создаем изображение через PIL
            img = Image.fromarray(arr)

            # Добавляем метаданные, если они переданы
            metadata = None
            if prompt is not None or extra_pnginfo is not None:
                metadata = PngImagePlugin.PngInfo()
                if prompt is not None:
                    metadata.add_text("prompt", json.dumps(prompt))
                if extra_pnginfo is not None:
                    for key, value in extra_pnginfo.items():
                        metadata.add_text(key, json.dumps(value))

            # Сохраняем изображение в буфер
            buffer = io.BytesIO()
            img.save(buffer, format="PNG", compress_level=self.compress_level, pnginfo=metadata)
            buffer.seek(0)
            image_bytes = buffer.getvalue()

            # Отладочная информация: SHA256 и размер
            sha256_hash = hashlib.sha256(image_bytes).hexdigest()
            print(f"[SaveImageToS3] SHA256 изображения: {sha256_hash}")
            print(f"[SaveImageToS3] Размер изображения: {len(image_bytes)} байт")

            # Формируем ключ для S3: folder/filename
            s3_key = f"{folder}/{filename}"

            try:
                s3_client.put_object(
                    Body=image_bytes,
                    Bucket=s3_bucket,
                    Key=s3_key,
                )
                upload_url = f"{s3_endpoint}/{s3_bucket}/{s3_key}"
                results.append({"filename": filename, "upload_url": upload_url, "status": "success"})
                print(f"[SaveImageToS3] Успешно загружено в S3: {upload_url}")
            except Exception as e:
                results.append({"filename": filename, "error": str(e)})
                print(f"[SaveImageToS3] Ошибка при загрузке в S3: {e}")

        print("Results:", results)
        return (images[0],)
