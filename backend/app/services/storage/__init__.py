"""对象存储抽象层。

`BaseStorage` 定义"放/取/签名 URL"三个核心操作；运行时根据
`settings.minio_enabled` 选择 `DbStorage`（content 直接存 ExportFile.content）
或 `MinIOStorage`（上传到 MinIO bucket，file_url 改为预签名 URL）。

这种抽象让 exports endpoint 不需要感知后端 storage 类型，未来再加 S3 / GCS
provider 也只是新增一个实现。
"""
from .base import BaseStorage, get_storage

__all__ = ["BaseStorage", "get_storage"]
