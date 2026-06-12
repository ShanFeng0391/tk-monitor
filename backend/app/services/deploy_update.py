"""Web 触发的本节点代码更新（后台 detached 进程，避免与 uvicorn 同进程）。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import PROJECT_ROOT, get_settings

settings = get_settings()

STATUS_FILE = Path(settings.data_dir) / "deploy-update-status.json"
LOG_FILE = Path(settings.data_dir) / "logs" / "deploy-update.log"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _read_status() -> dict[str, Any]:
    if not STATUS_FILE.is_file():
        return {}
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _write_status(payload: dict[str, Any]) -> None:
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _log_tail(max_lines: int = 40) -> str:
    if not LOG_FILE.is_file():
        return ""
    try:
        lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-max_lines:])
    except OSError:
        return ""


def _script_hint() -> str:
    if sys.platform == "win32":
        if (PROJECT_ROOT / ".env.hybrid").is_file():
            return r".\scripts\update.ps1"
        return r".\scripts\update.ps1"
    return "bash scripts/tencent-lightweight/update-code.sh"


def get_deploy_update_status() -> dict[str, Any]:
    raw = _read_status()
    state = raw.get("state") or "idle"
    started = raw.get("started_at")
    if state == "running" and started:
        try:
            started_dt = datetime.fromisoformat(str(started))
            if (_utcnow() - started_dt).total_seconds() > 3600:
                state = "failed"
                raw["message"] = raw.get("message") or "更新超时（超过 1 小时）"
        except ValueError:
            pass

    return {
        "enabled": settings.web_deploy_update_enabled,
        "state": state,
        "message": raw.get("message") or "",
        "started_at": raw.get("started_at"),
        "finished_at": raw.get("finished_at"),
        "log_tail": _log_tail(),
        "node_label": settings.compute_node_label or settings.compute_node_id,
        "script_hint": _script_hint(),
        "peer_hint": (
            "双节点：本按钮只更新当前浏览器所连的这台 API。"
            " 另一台请在其 Web 集群监控页各点一次，或 SSH 运行 update 脚本。"
        ),
    }


def trigger_deploy_update(
    *,
    backend_only: bool = False,
    frontend_only: bool = False,
    skip_git_pull: bool = False,
    quick: bool = True,
) -> dict[str, Any]:
    if not settings.web_deploy_update_enabled:
        raise PermissionError("Web 一键更新未开启，请在 .env 设置 WEB_DEPLOY_UPDATE_ENABLED=true")

    current = get_deploy_update_status()
    if current["state"] == "running":
        raise RuntimeError("已有更新任务在进行中，请稍后再试")

    if backend_only and frontend_only:
        raise ValueError("不能同时选择仅后端与仅前端")

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    started_at = _utcnow().isoformat()
    _write_status(
        {
            "state": "running",
            "message": "更新任务已启动",
            "started_at": started_at,
            "finished_at": None,
        }
    )

    if sys.platform == "win32":
        wrapper = PROJECT_ROOT / "scripts" / "web-trigger-update.ps1"
        if not wrapper.is_file():
            raise FileNotFoundError(f"缺少脚本: {wrapper}")
        cmd = [
            "powershell.exe",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(wrapper),
        ]
        if backend_only:
            cmd.append("-BackendOnly")
        if frontend_only:
            cmd.append("-FrontendOnly")
        if skip_git_pull:
            cmd.append("-SkipGitPull")
        if quick:
            cmd.append("-Quick")
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
        subprocess.Popen(
            cmd,
            cwd=str(PROJECT_ROOT),
            creationflags=creationflags,
            close_fds=True,
        )
    else:
        wrapper = PROJECT_ROOT / "scripts" / "web-trigger-update.sh"
        if not wrapper.is_file():
            raise FileNotFoundError(f"缺少脚本: {wrapper}")
        cmd = ["bash", str(wrapper)]
        if backend_only:
            cmd.append("--backend-only")
        if skip_git_pull:
            cmd.append("--skip-git")
        with open(LOG_FILE, "a", encoding="utf-8") as log_fp:
            log_fp.write(f"\n--- web trigger {_utcnow().isoformat()} ---\n")
            subprocess.Popen(
                cmd,
                cwd=str(PROJECT_ROOT),
                stdout=log_fp,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )

    return {
        "ok": True,
        "message": "更新已在后台启动，约 1～3 分钟。期间本页可能短暂无法访问，完成后请刷新。",
        "started_at": started_at,
    }
