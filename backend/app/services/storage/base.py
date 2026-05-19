"""对象存储抽象层 base 实现。

Sprint 5-B 阶段所有导出内容直接存 ExportFile.content；Sprint 6 引入
MinIO 后通过 enabled flag 切换到对象存储。两套实现共用同一接口，
exports endpoint 只与接口对话。
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Protocol

from app.core.config import get_settings


@dataclass(frozen=True)
class StoredObject:
    """storage put 之后返回的对象元信息。"""

    key: str  # 在 storage 内部的标识；db 模式下 = export_id
    size: int


class BaseStorage(Protocol):
    """统一的 put / get / sign_url 协议。"""

    async def put(self, key: str, content: bytes, *, content_type: str) -> StoredObject:
        """写入对象。key 一般是 `{org}/{project}/{export_id}.{suffix}`。"""

    async def get(self, key: str) -> bytes:
        """读出对象字节。db 模式下从 ExportFile.content 取；MinIO 模式下从 bucket 取。"""

    async def sign_url(self, key: str, filename: str, content_type: str) -> str | None:
        """返回带认证的下载 URL。db 模式返回 None（让 endpoint 走 stream）；
        MinIO 模式返回预签名 URL。"""


class _DbStorage:
    """默认 storage：内容直接存在 ExportFile.content，不与本类交互。

    保留 BaseStorage 接口便于将来 exports endpoint 用同一调用面；
    实际写入由 endpoint 完成。get/sign_url 不在 db 模式下被调用。
    """

    async def put(self, key: str, content: bytes, *, content_type: str) -> StoredObject:
        return StoredObject(key=key, size=len(content))

    async def get(self, key: str) -> bytes:
        raise NotImplementedError("DbStorage.get should not be called; endpoint reads ExportFile.content")

    async def sign_url(self, key: str, filename: str, content_type: str) -> str | None:
        return None


class _MinIOStorage:
    """MinIO / S3-compatible 实现。

    上传时 bucket 不存在会自动创建；预签名 URL 用 minio Python SDK 的
    `presigned_get_object`，默认 1 小时 TTL（由 settings.minio_presigned_ttl_seconds
    控制）。
    """

    def __init__(self) -> None:
        # lazy import：未启用 MinIO 时不导入 minio 库，避免增加冷启动时间。
        from minio import Minio

        settings = get_settings()
        self._client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_secure,
        )
        self._bucket = settings.minio_bucket
        self._presigned_ttl = settings.minio_presigned_ttl_seconds
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        if not self._client.bucket_exists(self._bucket):
            self._client.make_bucket(self._bucket)

    async def put(self, key: str, content: bytes, *, content_type: str) -> StoredObject:
        # minio SDK 是同步的；为简化先用同步调用。生产高并发时可换 aioboto3。
        self._client.put_object(
            self._bucket,
            key,
            io.BytesIO(content),
            length=len(content),
            content_type=content_type,
        )
        return StoredObject(key=key, size=len(content))

    async def get(self, key: str) -> bytes:
        resp = self._client.get_object(self._bucket, key)
        try:
            return resp.read()
        finally:
            resp.close()
            resp.release_conn()

    async def sign_url(self, key: str, filename: str, content_type: str) -> str | None:
        from datetime import timedelta

        # response_header_override：把 Content-Disposition 注入预签名响应，
        # 浏览器直接下载而非内联显示。
        return self._client.presigned_get_object(
            self._bucket,
            key,
            expires=timedelta(seconds=self._presigned_ttl),
            response_headers={
                "response-content-disposition": f'attachment; filename="{filename}"',
                "response-content-type": content_type,
            },
        )


_storage_instance: BaseStorage | None = None


def get_storage() -> BaseStorage:
    """工厂方法：按 settings.minio_enabled 返回对应 storage 实例（单例）。

    切换 enabled 配置需要重启进程（与 ModelGateway settings 不同——存储
    后端切换涉及历史数据迁移，不适合热切换）。
    """
    global _storage_instance
    if _storage_instance is not None:
        return _storage_instance
    settings = get_settings()
    if settings.minio_enabled:
        _storage_instance = _MinIOStorage()
    else:
        _storage_instance = _DbStorage()
    return _storage_instance


def reset_storage() -> None:
    """测试用：清掉单例缓存。"""
    global _storage_instance
    _storage_instance = None
