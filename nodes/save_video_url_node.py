import io
import os
import json
import numpy as np
import torch
import hashlib
import tempfile

from PIL import Image
import imageio
import boto3
from botocore.client import Config

class SaveVideoToS3:
    def __init__(self):
        self.type = "output"
        # Предустановки для FFmpeg, аналогичные параметру method в WebP-ноды
        self.ffmpeg_presets = {
            "default": "medium",
            "fastest": "ultrafast",
            "slowest": "veryslow"
        }

    @classmethod
    def INPUT_TYPES(cls):
        # Параметры заданы в алфавитном порядке для корректного сопоставления значений.
        return {
            "required": {
                "filename": ("STRING", {"default": "ComfyUI.mp4", "tooltip": "Имя файла для MP4."}),
                "fps": ("FLOAT", {"default": 6.0, "min": 0.01, "max": 1000.0, "step": 0.01, "tooltip": "Частота кадров (fps)."}),
                "folder": ("STRING", {"default": "ddcn_results", "tooltip": "Папка (на сервере), куда сохранять видео."}),
                "images": ("IMAGE", {"tooltip": "Кадры (тензоры) для формирования видео."}),
                "lossless": ("BOOLEAN", {"default": True, "tooltip": "Если True, CRF=0 (максимальное качество)."}),
                "method": (list(["default", "fastest", "slowest"]), {"tooltip": "FFmpeg preset: fastest=ultrafast, slowest=veryslow, default=medium."}),
                "quality": ("INT", {"default": 80, "min": 0, "max": 100, "tooltip": "Условный уровень качества (0=низкое, 100=высокое)."}),
                "s3_access_key": ("STRING", {"tooltip": "Access key для S3."}),
                "s3_bucket": ("STRING", {"tooltip": "Имя S3 Bucket."}),
                "s3_endpoint": ("STRING", {"tooltip": "S3 Endpoint URL, например: https://s3.amazonaws.com или иной."}),
                "s3_region": ("STRING", {"default": "us-east-1", "tooltip": "Регион S3."}),
                "s3_secret_key": ("STRING", {"tooltip": "Secret key для S3."}),
            },
            "hidden": {
                "prompt": "PROMPT",
                "extra_pnginfo": "EXTRA_PNGINFO"
            },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    OUTPUT_NODE = True
    FUNCTION = "save_video"
    CATEGORY = "video"

    DESCRIPTION = (
        "Формирует MP4-видео из входных кадров и загружает его на S3. "
        "Параметры сохранения (lossless, quality, method, fps) передаются в FFmpeg через imageio. "
        "Метаданные (prompt, extra_pnginfo) сохраняются в Metadata на S3. "
        "Возвращает первый кадр как IMAGE для продолжения цепочки."
    )

    def save_video(
        self,
        filename,
        fps,
        folder,
        images,
        lossless,
        method,
        quality,
        s3_access_key,
        s3_bucket,
        s3_endpoint,
        s3_region,
        s3_secret_key,
        prompt=None,
        extra_pnginfo=None
    ):
        """
        :param filename: Имя файла для MP4.
        :param fps: Частота кадров видео.
        :param folder: Папка на S3 для сохранения видео.
        :param images: Список тензоров (формат (C,H,W) или (H,W,C)).
        :param lossless: Если True, используется CRF=0 (максимальное качество).
        :param method: Один из ['default', 'fastest', 'slowest'] – выбор FFmpeg preset.
        :param quality: Условный уровень качества (0..100), преобразуется в CRF для x264.
        :param s3_access_key: Access key для S3.
        :param s3_bucket: Имя S3 Bucket.
        :param s3_endpoint: S3 Endpoint URL.
        :param s3_region: Регион S3 (например, "us-east-1").
        :param s3_secret_key: Secret key для S3.
        :param prompt: (hidden) Текстовый prompt для метаданных.
        :param extra_pnginfo: (hidden) Дополнительные метаданные (словарь).
        :return: (images[0],) – первый кадр как IMAGE.
        """

        # Инициализация S3 клиента
        s3_client = boto3.client(
            's3',
            endpoint_url=s3_endpoint,
            aws_access_key_id=s3_access_key,
            aws_secret_access_key=s3_secret_key,
            region_name=s3_region,
            config=Config(s3={'addressing_style': 'path'})
        )

        # Преобразуем тензоры в кадры (numpy-массивы)
        frames_all = []
        for image_tensor in images:
            arr = 255.0 * image_tensor.cpu().numpy()
            arr = np.clip(arr, 0, 255).astype(np.uint8)
            if arr.ndim == 3 and arr.shape[0] in [1, 3, 4]:
                arr = np.transpose(arr, (1, 2, 0))
            frames_all.append(arr)

        # Определяем FFmpeg preset (method)
        preset = self.ffmpeg_presets.get(method, "medium")

        # Рассчитываем CRF на основе lossless/quality
        if lossless:
            crf = 0
        else:
            crf = 51 - int(quality * 51 / 100)
            crf = max(0, min(51, crf))

        # Создаем временный файл для записи видео
        ext = os.path.splitext(filename)[1]
        if not ext:
            ext = ".mp4"
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp_file:
            temp_filename = tmp_file.name

        try:
            with imageio.get_writer(
                temp_filename,
                fps=fps,
                codec='libx264',
                format='FFMPEG',
                pixelformat='yuv420p',
                ffmpeg_params=['-preset', preset, '-crf', str(crf)]
            ) as writer:
                for frame in frames_all:
                    writer.append_data(frame)
            with open(temp_filename, "rb") as f:
                video_bytes = f.read()
        finally:
            if os.path.exists(temp_filename):
                os.remove(temp_filename)

        sha256_hash = hashlib.sha256(video_bytes).hexdigest()
        print(f"[SaveVideoToS3] MP4 {filename} SHA256: {sha256_hash}")
        print(f"[SaveVideoToS3] Размер: {len(video_bytes)} байт")

        metadata = {}
        if prompt is not None:
            metadata["prompt"] = json.dumps(prompt)
        if extra_pnginfo is not None:
            for k, v in extra_pnginfo.items():
                metadata[k] = json.dumps(v)

        s3_key = f"{folder}/{filename}"

        try:
            s3_client.put_object(
                Body=video_bytes,
                Bucket=s3_bucket,
                Key=s3_key,
                Metadata=metadata
            )
            upload_url = f"{s3_endpoint}/{s3_bucket}/{s3_key}"
            print(f"[SaveVideoToS3] Успешно загружено: {upload_url}")
        except Exception as e:
            print(f"[SaveVideoToS3] Ошибка загрузки: {e}")

        if len(images) > 0:
            return (images[0],)
        else:
            dummy = torch.zeros((3, 64, 64), dtype=torch.float32)
            return (dummy,)
