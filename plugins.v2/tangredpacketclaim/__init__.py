"""不可躺站点自动抢红包插件的 MoviePilot V2 实现。"""

import threading
import time
from typing import Any, Dict, List, Tuple

import requests
from apscheduler.triggers.cron import CronTrigger

from app.db.site_oper import SiteOper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import NotificationType


class TangRedPacketClaim(_PluginBase):
    """使用 V2 宿主接口获取并依次领取不可躺站点红包。"""

    plugin_name = "不可躺自动抢红包插件"
    plugin_desc = "自动在不可躺站点抢当前红包列表的所有红包，支持定时和立即执行。"
    plugin_icon = "https://raw.githubusercontent.com/jiongjiongJOJO/MoviePilot-Plugins/refs/heads/main/icons/tangredpacketclaim.png"
    plugin_version = "0.0.1"
    plugin_author = "jiongjiongJOJO"
    author_url = "https://github.com/jiongjiongJOJO"
    plugin_config_prefix = "tangredpacketclaim_"
    plugin_order = 30
    auth_level = 1

    SITE_DOMAINS = ("www.tangpt.top", "tangpt.top")
    LATEST_URL = "https://www.tangpt.top/api/redpacket/latest"
    CLAIM_URL = "https://www.tangpt.top/api/redpacket/claim"
    CLAIM_DELAY_SECONDS = 1
    MAX_FETCH_ROUNDS = 20

    _enabled = False
    _cron = "0 2,23 * * *"
    _notify = True
    _lock = threading.Lock()
    _last_result: Dict[str, Any] = {}

    def init_plugin(self, config: dict = None):
        """读取 V2 配置并消费一次性立即执行开关。"""
        config = config or {}
        self._lock = threading.Lock()
        self._enabled = bool(config.get("enabled", False))
        self._cron = str(config.get("cron") or "0 2,23 * * *").strip()
        self._notify = bool(config.get("notify", True))
        if config.get("run_once"):
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
    def get_command() -> List[Dict[str, Any]]:
        """不注册远程命令，使用配置页触发立即执行。"""
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        """V2 插件不暴露额外 API。"""
        return []

    def get_service(self) -> List[Dict[str, Any]]:
        """启用且 Cron 有效时注册定时任务。"""
        if not self._enabled or not self._cron:
            return []
        try:
            trigger = CronTrigger.from_crontab(self._cron)
        except ValueError:
            logger.warn("不可躺自动抢红包插件 Cron 配置无效，定时服务未注册")
            return []
        return [{
            "id": "TangRedPacketClaim",
            "name": "不可躺自动抢红包",
            "trigger": trigger,
            "func": self.run_red_packet_task,
            "kwargs": {},
        }]

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """返回 V2 配置页。"""
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
                    "text": "Cookie 只读取站点管理中 www.tangpt.top 或 tangpt.top 的 Cookie。",
                },
            }],
        }], {"enabled": False, "cron": "0 2,23 * * *", "notify": True, "run_once": False}

    def get_page(self) -> List[dict]:
        """显示最近一次任务结果。"""
        result = self._last_result or {"message": "尚未执行"}
        return [{
            "component": "VAlert",
            "props": {
                "type": "info", "variant": "tonal",
                "text": "定时：{}\n最近结果：{}".format(self._cron, result.get("message", "尚未执行")),
            },
        }]

    def stop_service(self):
        """释放插件自身资源；定时任务由宿主管理。"""
        return None

    def run_red_packet_task(self) -> Dict[str, Any]:
        """串行执行抢红包任务并发送可选通知。"""
        if not self._lock.acquire(blocking=False):
            return {"status": "running", "message": "已有抢红包任务正在执行"}
        try:
            cookie = self.__get_site_cookie()
            if not cookie or "c_secure_pass=" not in cookie:
                result = {"status": "auth_failed", "message": "不可躺站点 Cookie 未配置或已失效"}
            else:
                result = self.__claim_all(cookie)
            self._last_result = result
            if self._notify and result.get("claimed", 0) > 0:
                self.post_message(
                    mtype=NotificationType.Plugin,
                    title="【不可躺自动抢红包】",
                    text=result["message"],
                )
            return result
        finally:
            self._lock.release()

    def __claim_all(self, cookie: str) -> Dict[str, Any]:
        """多轮刷新列表并累计领取红包获得的魔力值。"""
        claimed = 0
        magic_total = 0
        user_bonus_after = None
        seen = set()
        session = requests.Session()
        session.headers.update({
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": "https://www.tangpt.top/index.php",
            "X-Requested-With": "XMLHttpRequest",
        })
        session.cookies.update(self.__cookie_to_dict(cookie))
        for _ in range(self.MAX_FETCH_ROUNDS):
            try:
                response = session.get(self.LATEST_URL, timeout=30)
                data = response.json()
            except (requests.RequestException, ValueError) as error:
                logger.error("获取不可躺红包列表失败：{}".format(error))
                return {"status": "request_failed", "message": "获取红包列表失败"}
            if not isinstance(data, dict) or data.get("ok") is not True:
                return {"status": "request_failed", "message": "获取红包列表失败"}
            items = data.get("items") or []
            logger.info("不可躺红包列表：本轮 {} 个，接口总数 {}".format(len(items), data.get("total_packet_count", "未知")))
            if not items:
                return self.__result("completed", "任务完成，共成功领取 {} 个红包".format(claimed), claimed, magic_total, user_bonus_after)
            for packet in items:
                packet_id = str(packet.get("id") or "")
                if not packet_id or packet_id in seen or packet.get("remain_count", 0) <= 0:
                    continue
                seen.add(packet_id)
                try:
                    claim_response = session.post(
                        self.CLAIM_URL,
                        data={"packet_id": packet_id},
                        timeout=30,
                    )
                    result = claim_response.json()
                except (requests.RequestException, ValueError) as error:
                    logger.warning("红包 {} 领取请求失败：{}".format(packet_id, error))
                    continue
                if not isinstance(result, dict) or result.get("ok") is not True:
                    message = str((result or {}).get("message") or "领取失败")
                    if "每天最多领" in message or ("已经领取" in message and "最多" in message):
                        return self.__result("limit_reached", message, claimed, magic_total, user_bonus_after)
                    logger.warning("红包 {} 领取失败：{}".format(packet_id, message))
                    continue
                amount = self.__safe_int(result.get("magic_amount"))
                claimed += 1
                magic_total += amount
                user_bonus_after = result.get("user_bonus_after", user_bonus_after)
                logger.info("红包 {} 领取成功：本次获得 {} 魔力值{}".format(
                    packet_id,
                    amount,
                    "，领取后魔力值 {}".format(user_bonus_after)
                    if user_bonus_after is not None else "",
                ))
                time.sleep(self.CLAIM_DELAY_SECONDS)
        return self.__result("completed", "达到刷新轮数上限", claimed, magic_total, user_bonus_after)

    @staticmethod
    def __result(status: str, message: str, claimed: int, magic_total: int, balance: Any) -> Dict[str, Any]:
        """构造包含魔力统计的任务结果。"""
        return {
            "status": status,
            "message": "{}，本轮获得魔力值 {}{}".format(
                message,
                magic_total,
                "，领取后魔力值 {}".format(balance) if balance is not None else "",
            ),
            "claimed": claimed,
            "magic_total": magic_total,
            "user_bonus_after": balance,
        }

    @classmethod
    def __get_site_cookie(cls) -> str:
        """按完整域名和根域名顺序读取站点 Cookie。"""
        for domain in cls.SITE_DOMAINS:
            try:
                site = SiteOper().get_by_domain(domain)
                cookie = str(getattr(site, "cookie", "") or "").strip() if site else ""
                if cookie:
                    return cookie
            except Exception as error:
                logger.debug("读取不可躺站点 Cookie 失败：domain={}，错误={}".format(domain, error))
        return ""

    @staticmethod
    def __cookie_to_dict(cookie: str) -> Dict[str, str]:
        """将 Cookie 字符串转换为 requests Cookie 字典。"""
        result = {}
        for item in (cookie or "").split(";"):
            if "=" not in item:
                continue
            key, value = item.split("=", 1)
            if key.strip():
                result[key.strip()] = value.strip()
        return result

    @staticmethod
    def __safe_int(value: Any) -> int:
        """将接口数值安全转换为整数。"""
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0
