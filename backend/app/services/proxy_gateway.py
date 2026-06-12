"""vmess/vless → 本地 SOCKS5：通过 sing-box 子进程转换。"""
from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import ProxyEndpoint
from app.services.proxy_link_parser import vmess_to_singbox_outbound, vless_to_singbox_outbound
from app.services.proxy_pool import proxy_pool

logger = logging.getLogger(__name__)
settings = get_settings()

_process: subprocess.Popen | None = None
_last_error: str | None = None


def gateway_config_dir() -> Path:
    path = Path(settings.data_dir) / "singbox"
    path.mkdir(parents=True, exist_ok=True)
    return path


def gateway_config_path() -> Path:
    return gateway_config_dir() / "config.json"


def find_singbox_bin() -> str | None:
    if settings.singbox_bin:
        candidate = Path(settings.singbox_bin)
        if candidate.is_file():
            return str(candidate)
    bundled = Path(settings.data_dir) / "bin" / "sing-box.exe"
    if bundled.is_file():
        return str(bundled)
    bundled_unix = Path(settings.data_dir) / "bin" / "sing-box"
    if bundled_unix.is_file():
        return str(bundled_unix)
    for name in ("sing-box", "sing-box.exe"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _config_marker() -> str:
    return str(gateway_config_path()).replace("\\", "/")


def _list_singbox_pids() -> list[int]:
    marker = _config_marker().lower()
    bin_name = Path(find_singbox_bin() or "sing-box.exe").name.lower()
    pids: list[int] = []
    if sys.platform == "win32":
        try:
            result = subprocess.run(
                ["wmic", "process", "where", f"name='{bin_name}'", "get", "ProcessId,CommandLine"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            for line in result.stdout.splitlines():
                lower = line.lower()
                if marker in lower or "singbox\\config.json" in lower:
                    match = re.search(r"(\d+)\s*$", line.strip())
                    if match:
                        pids.append(int(match.group(1)))
        except Exception as exc:
            logger.debug("wmic sing-box scan failed: %s", exc)
    else:
        try:
            result = subprocess.run(["pgrep", "-f", marker], capture_output=True, text=True, check=False)
            pids.extend(int(x) for x in result.stdout.split() if x.strip().isdigit())
        except Exception as exc:
            logger.debug("pgrep sing-box scan failed: %s", exc)
    return sorted(set(pids))


def _kill_pids(pids: list[int]) -> None:
    for pid in pids:
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, check=False)
            else:
                subprocess.run(["kill", "-9", str(pid)], capture_output=True, check=False)
        except Exception as exc:
            logger.debug("kill sing-box pid %s failed: %s", pid, exc)


def _singbox_appears_running(ports: list[int] | None = None) -> bool:
    if _process is not None and _process.poll() is None:
        return True
    if _list_singbox_pids():
        return True
    if not ports:
        return False
    if sys.platform == "win32":
        try:
            result = subprocess.run(["netstat", "-ano"], capture_output=True, text=True, check=False, timeout=10)
            listening: set[int] = set()
            for line in result.stdout.splitlines():
                if "127.0.0.1:" not in line or "LISTENING" not in line:
                    continue
                parts = line.split()
                if len(parts) < 5:
                    continue
                local = parts[1]
                for port in ports:
                    if local.endswith(f":{port}"):
                        listening.add(port)
            return len(listening) == len(ports)
        except Exception:
            return False
    return False


def gateway_status(ports: list[int] | None = None) -> dict[str, Any]:
    running = _singbox_appears_running(ports)
    bin_path = find_singbox_bin()
    return {
        "enabled": settings.singbox_enabled,
        "running": running,
        "bin_found": bool(bin_path),
        "bin_path": bin_path or "",
        "last_error": _last_error,
        "config_path": str(gateway_config_path()),
    }


def stop_singbox() -> None:
    global _process, _last_error
    if _process is not None:
        if _process.poll() is None:
            _process.terminate()
            try:
                _process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                _process.kill()
                _process.wait(timeout=3)
        _process = None
    orphan_pids = _list_singbox_pids()
    if orphan_pids:
        logger.info("Stopping orphaned sing-box processes: %s", orphan_pids)
        _kill_pids(orphan_pids)
        time.sleep(0.5)


def _inbound_tag(proxy_id: int) -> str:
    return f"in-{proxy_id}"


def _outbound_tag(proxy_id: int) -> str:
    return f"out-{proxy_id}"


def build_singbox_config(rows: list[ProxyEndpoint]) -> dict[str, Any]:
    inbounds: list[dict[str, Any]] = []
    outbounds: list[dict[str, Any]] = []
    rules: list[dict[str, Any]] = []

    for row in rows:
        if row.protocol not in ("vmess", "vless") or not row.raw_uri or not row.local_socks_port:
            continue
        in_tag = _inbound_tag(row.id)
        out_tag = _outbound_tag(row.id)
        inbounds.append(
            {
                "type": "socks",
                "tag": in_tag,
                "listen": "127.0.0.1",
                "listen_port": row.local_socks_port,
            }
        )
        if row.protocol == "vmess":
            outbounds.append(vmess_to_singbox_outbound(row.raw_uri, out_tag))
        else:
            outbounds.append(vless_to_singbox_outbound(row.raw_uri, out_tag))
        rules.append({"inbound": [in_tag], "outbound": out_tag})

    outbounds.extend(
        [
            {"type": "direct", "tag": "direct"},
            {"type": "block", "tag": "block"},
        ]
    )
    return {
        "log": {"level": "warn", "timestamp": True},
        "inbounds": inbounds,
        "outbounds": outbounds,
        "route": {"rules": rules, "final": "block"},
    }


def start_singbox(config: dict[str, Any]) -> None:
    global _process, _last_error

    if not settings.singbox_enabled:
        _last_error = "sing-box 网关未启用（SINGBOX_ENABLED=false）"
        stop_singbox()
        return

    if not config.get("inbounds"):
        stop_singbox()
        _last_error = None
        return

    bin_path = find_singbox_bin()
    if not bin_path:
        _last_error = (
            "未找到 sing-box 可执行文件。请安装 sing-box 并加入 PATH，"
            "或在环境变量 SINGBOX_BIN 中指定路径。"
        )
        raise RuntimeError(_last_error)

    config_path = gateway_config_path()
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

    stop_singbox()
    kwargs: dict[str, Any] = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    proc = subprocess.Popen(
        [bin_path, "run", "-c", str(config_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        **kwargs,
    )
    _process = proc

    # 短暂等待，确认进程未立即退出
    try:
        rc = proc.wait(timeout=1.5)
    except subprocess.TimeoutExpired:
        _last_error = None
        logger.info("sing-box 已启动，监听 %d 个本地 SOCKS5 端口", len(config["inbounds"]))
        return

    stderr = (proc.stderr.read() if proc.stderr else b"").decode("utf-8", errors="replace")
    _process = None
    _last_error = stderr.strip() or f"sing-box 启动失败，退出码 {rc}"
    raise RuntimeError(_last_error)


def assign_local_port(proxy_id: int) -> int:
    return settings.proxy_gateway_base_port + proxy_id


async def sync_from_db(db: AsyncSession) -> dict[str, Any]:
    """根据数据库中的 vmess/vless 节点重建 sing-box 配置并重启。"""
    global _last_error
    rows = await proxy_pool.list_proxies(db)
    gateway_rows = [
        row
        for row in rows
        if row.protocol in ("vmess", "vless") and row.raw_uri and row.local_socks_port
    ]
    ports = [row.local_socks_port for row in gateway_rows if row.local_socks_port]
    try:
        config = build_singbox_config(gateway_rows)
        start_singbox(config)
        return {
            **gateway_status(ports),
            "gateway_nodes": len(gateway_rows),
        }
    except RuntimeError as exc:
        logger.warning("sing-box 同步失败: %s", exc)
        return {
            **gateway_status(ports),
            "gateway_nodes": len(gateway_rows),
            "error": str(exc),
        }
