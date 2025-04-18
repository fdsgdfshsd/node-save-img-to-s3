# try:
#     from . import prestartup_script
# except Exception as e:
#     print(f"Ошибка при выполнении prepare_environment: {e}")

from .nodes.save_image_url_node import SaveImageToS3
from .nodes.save_video_url_node import SaveVideoToS3

NODE_CLASS_MAPPINGS = {
    "SaveImageToS3": SaveImageToS3,
    "SaveVideoToS3": SaveVideoToS3,
}
