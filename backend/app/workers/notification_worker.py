from __future__ import annotations

import asyncio


async def main() -> None:
    # notification_worker 占位：真实部署时连接 Temporal task queue 并注册对应 workflows/activities。
    print("notification_worker ready (stub)")


if __name__ == "__main__":
    asyncio.run(main())
