"""不可躺站点自动抢红包插件。"""

from __future__ import annotations

import threading
import time
from typing import Any

from apscheduler.triggers.cron import CronTrigger

from app.db.oper.site import SiteOper
from app.plugins import _PluginBase
from app.schemas import NotificationType
from app.sdk.logging import logger
from app.sdk.network import RequestUtils


class TangRedPacketClaim(_PluginBase):
    """从不可躺站点获取并依次领取当前可用红包。"""

    plugin_name = "不可躺自动抢红包插件"
    plugin_desc = "自动在不可躺站点抢当前红包列表的所有红包，支持定时和立即执行。"
    plugin_icon = "Moviepilot_A.png"
    plugin_version = "0.0.1"
    plugin_author = "jiongjiongJOJO"
    author_url = "https://github.com/jiongjiongJOJO"
    plugin_config_prefix = "tangredpacketclaim_"
    plugin_order = 30
    auth_level = 1

    SITE_DOMAIN = "www.tangpt.top"
    LATEST_URL = "https://www.tangpt.top/api/redpacket/latest"
    CLAIM_URL = "https://www.tangpt.top/api/redpacket/claim"
    CLAIM_DELAY_SECONDS = 1
    MAX_FETCH_ROUNDS = 20

    _enabled = False
    _cron = "0 2,23 * * *"
    _notify = True
    _run_once = False
    _lock = threading.Lock()
    _last_result: dict[str, Any] = {}

    def init_plugin(self, config: dict | None = None) -> None:
        """读取配置；立即执行开关只消费一次，支持宿主重复初始化。"""
        self.stop_service()
        self._lock = threading.Lock()
        config = config or {}
        self._enabled = bool(config.get("enabled", False))
        self._cron = str(config.get("cron") or "0 2,23 * * *").strip()
        self._notify = bool(config.get("notify", True))
        run_once = bool(config.get("run_once", False))
        if run_once:
            self.update_config({
                "enabled": self._enabled,
                "cron": self._cron,
                "notify": self._notify,
                "run_once": False,
            })
            threading.Thread(target=self.run_red_packet_task, daemon=True).start()

    def get_state(self) -> bool:
        """返回插件启用状态。"""
        return self._enabled

    @staticmethod
    def get_command() -> list[dict[str, Any]]:
        """不注册远程命令，立即执行通过配置开关触发。"""
        return []

    def get_api(self) -> list[dict[str, Any]]:
        """不暴露额外 API，避免增加不必要的执行入口。"""
        return []

    def get_service(self) -> list[dict[str, Any]]:
        """启用且 Cron 有效时注册宿主托管的定时任务。"""
        if not self._enabled or not self._cron:
            return []
        try:
            trigger = CronTrigger.from_crontab(self._cron)
        except ValueError:
            logger.warning("不可躺自动抢红包插件 Cron 配置无效，定时服务未注册")
            return []
        return [{
            "id": "TangRedPacketClaim",
            "name": "不可躺自动抢红包",
            "trigger": trigger,
            "func": self.run_red_packet_task,
            "kwargs": {},
        }]

    def get_form(self) -> tuple[list[dict], dict[str, Any]]:
        """返回启用、定时、通知和立即运行配置。"""
        return [{
            "component": "VForm",
            "content": [{
                "component": "VRow",
                "content": [
                    {"component": "VCol", "props": {"cols": 12, "md": 3}, "content": [{
                        "component": "VSwitch", "props": {"model": "enabled", "label": "启用插件"}
                    }]},
                    {"component": "VCol", "props": {"cols": 12, "md": 3}, "content": [{
                        "component": "VSwitch", "props": {"model": "notify", "label": "发送通知"}
                    }]},
                    {"component": "VCol", "props": {"cols": 12, "md": 3}, "content": [{
                        "component": "VSwitch", "props": {
                            "model": "run_once", "label": "立即运行一次", "hint": "保存配置后执行，并自动关闭"
                        }
                    }]},
                    {"component": "VCol", "props": {"cols": 12, "md": 3}, "content": [{
                        "component": "VCronField", "props": {
                            "model": "cron", "label": "执行周期", "placeholder": "例如 0 2,23 * * *"
                        }
                    }]},
                ],
            }, {
                "component": "VAlert",
                "props": {
                    "type": "info", "variant": "tonal",
                    "text": "Cookie 只读取站点管理中 www.tangpt.top 的 Cookie，请先在站点管理配置并测试登录。",
                },
            }],
        }], {"enabled": False, "cron": "0 2,23 * * *", "notify": True, "run_once": False}

    def get_page(self) -> list[dict]:
        """显示最近一次任务结果和当前定时配置。"""
        result = self._last_result or {"message": "尚未执行"}
        return [{
            "component": "VAlert",
            "props": {
                "type": "info", "variant": "tonal",
                "text": f"定时：{self._cron}\n最近结果：{result.get('message', '尚未执行')}",
            },
        }]

    def stop_service(self) -> None:
        """清理插件自身的运行状态；定时任务由宿主负责撤销。"""
        return None

    def run_red_packet_task(self) -> dict[str, Any]:
        """串行执行多轮列表刷新和领取，防止重复任务并尊重每日上限。"""
        if not self._lock.acquire(blocking=False):
            return {"status": "running", "message": "已有抢红包任务正在执行"}
        try:
            cookie = self._get_site_cookie()
            if not cookie or "c_secure_pass=" not in cookie:
                result = {"status": "auth_failed", "message": "不可躺站点 Cookie 未配置或已失效"}
            else:
                result = self._claim_all(cookie)
            self._last_result = result
            if self._notify:
                self.post_message(
                    mtype=NotificationType.Plugin,
                    title="【不可躺自动抢红包】",
                    text=f"状态：{result['status']}\n消息：{result['message']}",
                )
            return result
        finally:
            self._lock.release()

    def _claim_all(self, cookie: str) -> dict[str, Any]:
        """按列表为空、领取失败或每日上限停止多轮抢红包，并累计本轮魔力值。"""
        claimed = 0
        magic_total = 0
        user_bonus_after: Any = None
        seen: set[str] = set()
        request = RequestUtils(cookies=self._cookie_to_dict(cookie), headers={
            "accept": "application/json, text/javascript, */*; q=0.01",
            "referer": "https://www.tangpt.top/index.php",
            "x-requested-with": "XMLHttpRequest",
        })
        for _ in range(self.MAX_FETCH_ROUNDS):
            data = request.get_json(self.LATEST_URL)
            if not isinstance(data, dict) or data.get("ok") is not True:
                return {"status": "request_failed", "message": "获取红包列表失败"}
            items = data.get("items") or []
            total_packet_count = data.get("total_packet_count")
            logger.info(
                f"不可躺红包列表：本轮 {len(items)} 个，接口总数 "
                f"{total_packet_count if total_packet_count is not None else '未知'}"
            )
            if not items:
                return self._build_result(
                    "completed", f"任务完成，共成功领取 {claimed} 个红包",
                    claimed, magic_total, user_bonus_after,
                )
            for packet in items:
                packet_id = str(packet.get("id") or "")
                if not packet_id or packet_id in seen or packet.get("remain_count", 0) <= 0:
                    continue
                seen.add(packet_id)
                claim = request.post_res(
                    self.CLAIM_URL,
                    data={"packet_id": packet_id},
                    headers={"content-type": "application/x-www-form-urlencoded; charset=UTF-8"},
                )
                result = claim.json() if claim else None
                if not isinstance(result, dict) or result.get("ok") is not True:
                    message = str((result or {}).get("message") or "领取失败")
                    if "每天最多领" in message or "已经领取" in message and "最多" in message:
                        return self._build_result(
                            "limit_reached", message, claimed, magic_total, user_bonus_after,
                        )
                    logger.warning(f"红包 {packet_id} 领取失败：{message}")
                    continue
                claimed += 1
                magic_amount = self._safe_int(result.get("magic_amount"))
                magic_total += magic_amount
                user_bonus_after = result.get("user_bonus_after", user_bonus_after)
                logger.info(
                    f"红包 {packet_id} 领取成功：本次获得 {magic_amount} 魔力值，"
                    f"领取后魔力值 {user_bonus_after if user_bonus_after is not None else '未知'}"
                )
                time.sleep(self.CLAIM_DELAY_SECONDS)
        return self._build_result(
            "completed", "达到刷新轮数上限", claimed, magic_total, user_bonus_after,
        )

    @staticmethod
    def _build_result(
        status: str,
        message: str,
        claimed: int,
        magic_total: int,
        user_bonus_after: Any,
    ) -> dict[str, Any]:
        """构造任务结果，统一输出红包数量、总魔力值和领取后余额。"""
        balance = user_bonus_after if user_bonus_after is not None else "未知"
        return {
            "status": status,
            "message": (
                f"{message}，本轮获得魔力值 {magic_total}，"
                f"领取后魔力值 {balance}"
            ),
            "claimed": claimed,
            "magic_total": magic_total,
            "user_bonus_after": user_bonus_after,
        }

    @staticmethod
    def _safe_int(value: Any) -> int:
        """将接口中的魔力数值安全转换为整数。"""
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _cookie_to_dict(cookie: str) -> dict[str, str]:
        """将站点管理保存的 Cookie 字符串转换为请求参数。"""
        return {
            key.strip(): value.strip()
            for item in cookie.split(";")
            if "=" in item
            for key, value in [item.split("=", 1)]
            if key.strip()
        }

    @classmethod
    def _get_site_cookie(cls) -> str:
        """读取不可躺站点管理记录，不把 Cookie 写入插件配置。"""
        # 站点管理可能保存为完整域名，也可能保存为根域名，两种都兼容。
        for domain in (cls.SITE_DOMAIN, "tangpt.top"):
            try:
                site = SiteOper().get_by_domain(domain)
                cookie = str(getattr(site, "cookie", "") or "").strip() if site else ""
                if cookie:
                    return cookie
            except Exception as error:
                logger.debug(f"读取不可躺站点 Cookie 失败：domain={domain}，错误={error}")
        return ""
