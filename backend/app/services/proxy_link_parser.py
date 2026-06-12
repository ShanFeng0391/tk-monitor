"""解析 socks5 / vmess / vless 分享链接。"""
from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from app.services.proxy_pool import parse_socks5_label, parse_socks5_url


@dataclass
class ParsedShareLink:
    protocol: str  # socks5 | vmess | vless
    remote_host: str
    remote_port: int
    label: str = ""
    raw_uri: str = ""
    username: str = ""
    password: str = ""


def _b64decode_payload(data: str) -> bytes:
    raw = data.strip()
    raw += "=" * (-len(raw) % 4)
    try:
        return base64.b64decode(raw)
    except Exception:
        return base64.urlsafe_b64decode(raw)


def _first_qs(qs: dict[str, list[str]], key: str, default: str = "") -> str:
    values = qs.get(key) or []
    return unquote(values[0]).strip() if values else default


def parse_vmess(uri: str) -> ParsedShareLink:
    raw = uri.strip()
    if not raw.lower().startswith("vmess://"):
        raise ValueError("不是有效的 vmess:// 链接")
    payload = raw[8:]
    if "?" in payload:
        payload = payload.split("?", 1)[0]
    try:
        data: dict[str, Any] = json.loads(_b64decode_payload(payload).decode("utf-8"))
    except Exception as exc:
        raise ValueError("vmess 链接解码失败") from exc

    host = str(data.get("add") or "").strip()
    port_raw = data.get("port")
    try:
        port = int(port_raw)
    except (TypeError, ValueError) as exc:
        raise ValueError("vmess 缺少有效端口") from exc
    if not host:
        raise ValueError("vmess 缺少服务器地址")

    label = str(data.get("ps") or "").strip()
    if not label and "#" in raw:
        label = unquote(raw.split("#", 1)[1]).strip()

    return ParsedShareLink(
        protocol="vmess",
        remote_host=host,
        remote_port=port,
        label=label,
        raw_uri=raw,
    )


def parse_vless(uri: str) -> ParsedShareLink:
    raw = uri.strip()
    if not raw.lower().startswith("vless://"):
        raise ValueError("不是有效的 vless:// 链接")

    parsed = urlparse(raw)
    uuid = unquote(parsed.username or "").strip()
    host = (parsed.hostname or "").strip()
    port = parsed.port
    if not uuid:
        raise ValueError("vless 缺少 UUID")
    if not host:
        raise ValueError("vless 缺少服务器地址")
    if port is None:
        raise ValueError("vless 缺少端口")

    label = unquote(parsed.fragment or "").strip()
    return ParsedShareLink(
        protocol="vless",
        remote_host=host,
        remote_port=port,
        label=label,
        raw_uri=raw,
        username=uuid,
    )


def parse_socks_v2ray(uri: str) -> ParsedShareLink:
    """v2rayN 常用 socks:// + Base64(user:pass@host:port)。"""
    raw = uri.strip()
    if not raw.lower().startswith("socks://"):
        raise ValueError("不是有效的 socks:// 链接")

    label = parse_socks5_label(raw.replace("socks://", "socks5://", 1))
    body = raw[8:].split("#", 1)[0].split("?", 1)[0].strip()

    candidates = [body]
    try:
        decoded = _b64decode_payload(body).decode("utf-8", errors="replace").strip()
        if decoded:
            candidates.insert(0, decoded)
    except Exception:
        pass

    for candidate in candidates:
        if "://" in candidate:
            if candidate.lower().startswith("socks5://"):
                return parse_share_link(candidate)
            candidate = f"socks5://{candidate.split('://', 1)[-1]}"
        if not candidate.lower().startswith("socks5://"):
            candidate = f"socks5://{candidate.lstrip('/')}"
        try:
            host, port, username, password = parse_socks5_url(candidate)
            return ParsedShareLink(
                protocol="socks5",
                remote_host=host,
                remote_port=port,
                label=label,
                raw_uri=raw,
                username=username,
                password=password,
            )
        except ValueError:
            continue
    raise ValueError("socks:// 链接解码失败")


def parse_share_link(uri: str) -> ParsedShareLink:
    raw = uri.strip()
    if not raw:
        raise ValueError("链接不能为空")
    lower = raw.lower()
    if lower.startswith("socks5://"):
        host, port, username, password = parse_socks5_url(raw)
        label = parse_socks5_label(raw)
        return ParsedShareLink(
            protocol="socks5",
            remote_host=host,
            remote_port=port,
            label=label,
            raw_uri=raw,
            username=username,
            password=password,
        )
    if lower.startswith("socks://"):
        return parse_socks_v2ray(raw)
    if lower.startswith("vmess://"):
        return parse_vmess(raw)
    if lower.startswith("vless://"):
        return parse_vless(raw)
    raise ValueError("仅支持 socks5://、socks://、vmess://、vless:// 链接")


def vmess_to_singbox_outbound(raw_uri: str, tag: str) -> dict[str, Any]:
    parsed = parse_vmess(raw_uri)
    data: dict[str, Any] = json.loads(_b64decode_payload(raw_uri[8:].split("?", 1)[0]).decode("utf-8"))

    network = str(data.get("net") or "tcp").lower()
    tls_enabled = str(data.get("tls") or "").lower() == "tls"
    security = str(data.get("scy") or "auto").lower()
    if security in ("", "none", "zero"):
        security = "auto"

    outbound: dict[str, Any] = {
        "type": "vmess",
        "tag": tag,
        "server": parsed.remote_host,
        "server_port": parsed.remote_port,
        "uuid": str(data.get("id") or "").strip(),
        "alter_id": int(data.get("aid") or 0),
        "security": security,
    }
    if not outbound["uuid"]:
        raise ValueError("vmess 缺少 UUID")

    transport = _build_transport(network, data, is_vless=False)
    if transport:
        outbound["transport"] = transport

    outbound["tls"] = _build_tls(tls_enabled, data, parsed.remote_host, is_vless=False)
    return outbound


def vless_to_singbox_outbound(raw_uri: str, tag: str) -> dict[str, Any]:
    parsed = urlparse(raw_uri.strip())
    qs = parse_qs(parsed.query)
    uuid = unquote(parsed.username or "").strip()
    security = _first_qs(qs, "security").lower() or "none"
    network = _first_qs(qs, "type", "tcp").lower() or "tcp"
    flow = _first_qs(qs, "flow")

    outbound: dict[str, Any] = {
        "type": "vless",
        "tag": tag,
        "server": parsed.hostname,
        "server_port": parsed.port,
        "uuid": uuid,
    }
    if flow:
        outbound["flow"] = flow

    data = {
        "path": _first_qs(qs, "path", "/"),
        "host": _first_qs(qs, "host") or _first_qs(qs, "sni"),
        "sni": _first_qs(qs, "sni") or _first_qs(qs, "host"),
        "serviceName": _first_qs(qs, "serviceName") or _first_qs(qs, "serviceName"),
        "mode": _first_qs(qs, "mode"),
        "pbk": _first_qs(qs, "pbk"),
        "sid": _first_qs(qs, "sid"),
        "fp": _first_qs(qs, "fp"),
    }
    transport = _build_transport(network, data, is_vless=True)
    if transport:
        outbound["transport"] = transport

    tls_enabled = security in ("tls", "reality", "xtls")
    outbound["tls"] = _build_tls(
        tls_enabled,
        data,
        parsed.hostname or "",
        is_vless=True,
        security=security,
    )
    return outbound


def _build_transport(network: str, data: dict[str, Any], *, is_vless: bool) -> dict[str, Any] | None:
    if network in ("", "tcp", "none", "raw"):
        return None
    if network == "ws":
        path = str(data.get("path") or "/")
        host_header = str(data.get("host") or "").strip()
        transport: dict[str, Any] = {"type": "ws", "path": path}
        if host_header:
            transport["headers"] = {"Host": host_header}
        return transport
    if network == "grpc":
        service_name = str(
            data.get("serviceName") or data.get("path") or data.get("service_name") or ""
        ).strip()
        transport = {"type": "grpc"}
        if service_name:
            transport["service_name"] = service_name.lstrip("/")
        mode = str(data.get("mode") or "").strip()
        if mode:
            transport["idle_timeout"] = "15s"
        return transport
    if network in ("h2", "http"):
        path = str(data.get("path") or "/")
        host_header = str(data.get("host") or "").strip()
        transport = {"type": "http", "path": path}
        if host_header:
            transport["host"] = [host_header]
        return transport
    if not is_vless:
        raise ValueError(f"暂不支持的 vmess 传输类型: {network}")
    raise ValueError(f"暂不支持的 vless 传输类型: {network}")


def _build_tls(
    enabled: bool,
    data: dict[str, Any],
    fallback_sni: str,
    *,
    is_vless: bool,
    security: str = "tls",
) -> dict[str, Any]:
    sni = str(data.get("sni") or data.get("host") or fallback_sni or "").strip()
    fp = str(data.get("fp") or "").strip()

    if is_vless and security == "reality":
        pbk = str(data.get("pbk") or "").strip()
        sid = str(data.get("sid") or "").strip()
        if not pbk:
            raise ValueError("vless reality 缺少 pbk 参数")
        tls: dict[str, Any] = {
            "enabled": True,
            "server_name": sni or fallback_sni,
            "utls": {"enabled": True, "fingerprint": fp or "chrome"},
            "reality": {
                "enabled": True,
                "public_key": pbk,
                "short_id": sid,
            },
        }
        return tls

    if not enabled:
        return {"enabled": False}

    tls = {"enabled": True}
    if sni:
        tls["server_name"] = sni
    if fp:
        tls["utls"] = {"enabled": True, "fingerprint": fp}
    return tls


def detect_protocol(uri: str) -> str | None:
    lower = uri.strip().lower()
    if lower.startswith("socks5://"):
        return "socks5"
    if lower.startswith("socks://"):
        return "socks5"
    if lower.startswith("vmess://"):
        return "vmess"
    if lower.startswith("vless://"):
        return "vless"
    return None


def is_share_link(uri: str) -> bool:
    return detect_protocol(uri) is not None


def sanitize_label(text: str, max_len: int = 100) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    return cleaned[:max_len]
