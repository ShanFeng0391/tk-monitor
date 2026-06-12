"""代理网关自检：解析链接、生成 sing-box 配置、可选健康检查。"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.config import get_settings
from app.database import async_session
from app.services.proxy_gateway import (
    build_singbox_config,
    find_singbox_bin,
    gateway_config_path,
    gateway_status,
    sync_from_db,
)
from app.services.proxy_link_parser import parse_share_link
from app.services.proxy_pool import proxy_pool


async def _print_status() -> None:
    settings = get_settings()
    bin_path = find_singbox_bin()
    print("=== 代理网关状态 ===")
    print(f"DATA_DIR: {settings.data_dir}")
    print(f"SINGBOX_BIN 配置: {settings.singbox_bin or '(未设置)'}")
    print(f"实际二进制: {bin_path or '(未找到)'}")
    print(f"配置路径: {gateway_config_path()}")
    gw = gateway_status()
    print(f"运行中: {gw.get('running')}")
    print(f"最近错误: {gw.get('last_error') or '—'}")

    async with async_session() as db:
        rows = await proxy_pool.list_proxies(db)
        print(f"\n代理池节点: {len(rows)}")
        for row in rows:
            print(
                f"  #{row.id} {row.protocol or 'socks5':6} "
                f"{row.label or row.host}:{row.port} "
                f"local={row.local_socks_port or '-'} "
                f"status={row.health_status}"
            )
        gateway_rows = [
            r for r in rows if r.protocol in ("vmess", "vless") and r.local_socks_port
        ]
        if gateway_rows:
            config = build_singbox_config(gateway_rows)
            print(f"\n将生成 {len(config.get('inbounds', []))} 个本地 SOCKS5 入站")
        result = await sync_from_db(db)
        print("\n同步结果:", result)


async def _check_uri(uri: str) -> None:
    parsed = parse_share_link(uri)
    print("解析成功:")
    print(f"  协议: {parsed.protocol}")
    print(f"  远程: {parsed.remote_host}:{parsed.remote_port}")
    print(f"  备注: {parsed.label or '—'}")


async def _add_uri(uri: str, *, check: bool) -> None:
    parsed = parse_share_link(uri)
    async with async_session() as db:
        row = await proxy_pool.create_proxy(
            db,
            host=parsed.remote_host,
            port=parsed.remote_port,
            username=parsed.username,
            password=parsed.password,
            label=parsed.label,
            enabled=True,
            protocol=parsed.protocol,
            raw_uri=parsed.raw_uri or uri.strip(),
        )
        print(f"已添加节点 #{row.id} ({row.protocol})")
        if row.local_socks_port:
            print(f"  本地 SOCKS5: socks5://127.0.0.1:{row.local_socks_port}")
        if check:
            status = await proxy_pool.check_health(db, row)
            refreshed = await proxy_pool.get_proxy(db, row.id)
            print(f"  健康检查: {status}")
            if refreshed and refreshed.last_error:
                print(f"  错误: {refreshed.last_error}")


def main() -> None:
    parser = argparse.ArgumentParser(description="代理网关自检工具")
    parser.add_argument("--status", action="store_true", help="打印网关与池状态并同步")
    parser.add_argument("--parse", metavar="URI", help="仅解析分享链接")
    parser.add_argument("--add", metavar="URI", help="添加 vmess/vless/socks5 到代理池")
    parser.add_argument("--check", action="store_true", help="与 --add 联用，添加后立即健康检查")
    args = parser.parse_args()

    if args.parse:
        asyncio.run(_check_uri(args.parse))
        return
    if args.add:
        asyncio.run(_add_uri(args.add, check=args.check))
        return
    asyncio.run(_print_status())


if __name__ == "__main__":
    main()
