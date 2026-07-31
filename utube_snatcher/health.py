from __future__ import annotations

from aiohttp import web

from .storage import UsageStorage


async def start_health_server(
    storage: UsageStorage,
    *,
    host: str,
    port: int,
) -> web.AppRunner:
    async def health(_: web.Request) -> web.Response:
        return web.json_response(
            {
                "status": "ok",
                "maintenance": storage.maintenance_enabled(),
            }
        )

    app = web.Application()
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=host, port=port)
    await site.start()
    return runner
