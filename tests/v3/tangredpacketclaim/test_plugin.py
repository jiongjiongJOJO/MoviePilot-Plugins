"""不可躺自动抢红包插件的纯逻辑测试。"""

from types import SimpleNamespace
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch

# 第三方插件仓库不携带 MoviePilot 宿主，这里只为纯逻辑测试提供最小桩。
app = types.ModuleType("app")
app.__path__ = []
plugins = types.ModuleType("app.plugins")
plugins.__path__ = [str(Path(__file__).parents[3] / "plugins.v3")]
plugins._PluginBase = type("_PluginBase", (), {})
db = types.ModuleType("app.db")
oper = types.ModuleType("app.db.oper")
site = types.ModuleType("app.db.oper.site")
site.SiteOper = MagicMock()
schemas = types.ModuleType("app.schemas")
schemas.NotificationType = SimpleNamespace(Plugin="Plugin")
sdk = types.ModuleType("app.sdk")
logging = types.ModuleType("app.sdk.logging")
logging.logger = MagicMock()
network = types.ModuleType("app.sdk.network")
network.RequestUtils = MagicMock()
app.plugins = plugins
app.db = db
app.schemas = schemas
app.sdk = sdk
sdk.logging = logging
sdk.network = network
sys.modules.update({
    "app": app,
    "app.plugins": plugins,
    "app.db": db,
    "app.db.oper": oper,
    "app.db.oper.site": site,
    "app.schemas": schemas,
    "app.sdk": sdk,
    "app.sdk.logging": logging,
    "app.sdk.network": network,
})

from app.plugins.tangredpacketclaim import TangRedPacketClaim


def make_plugin() -> TangRedPacketClaim:
    """构造不触发宿主插件管理器的测试实例。"""
    plugin = object.__new__(TangRedPacketClaim)
    plugin._enabled = True
    plugin._cron = "0 2,23 * * *"
    plugin._notify = False
    plugin._last_result = {}
    plugin._lock = __import__("threading").Lock()
    return plugin


def test_cookie_to_dict() -> None:
    assert TangRedPacketClaim._cookie_to_dict("a=1; c_secure_pass=token; flag") == {
        "a": "1", "c_secure_pass": "token"
    }


def test_v3_required_lifecycle_api_is_present() -> None:
    """V3 插件必须实现基类要求的 get_api 方法，避免抽象类实例化失败。"""
    assert hasattr(TangRedPacketClaim, "get_api")
    assert not hasattr(TangRedPacketClaim, "get_apiget_api")


def test_empty_claim_result_does_not_trigger_notification() -> None:
    """定时任务没有成功领取红包时不应发送频繁通知。"""
    plugin = make_plugin()
    plugin._notify = True
    plugin.post_message = MagicMock()

    with patch.object(plugin, "_get_site_cookie", return_value="c_secure_pass=token"), patch.object(
        plugin, "_claim_all", return_value={"status": "completed", "message": "没有可领取红包", "claimed": 0}
    ):
        result = plugin.run_red_packet_task()

    assert result["claimed"] == 0
    plugin.post_message.assert_not_called()


def test_successful_claim_result_triggers_notification() -> None:
    """至少成功领取一个红包时仍应发送任务结果通知。"""
    plugin = make_plugin()
    plugin._notify = True
    plugin.post_message = MagicMock()

    with patch.object(plugin, "_get_site_cookie", return_value="c_secure_pass=token"), patch.object(
        plugin, "_claim_all", return_value={"status": "completed", "message": "成功", "claimed": 1}
    ):
        plugin.run_red_packet_task()

    plugin.post_message.assert_called_once()
    assert plugin.post_message.call_args.kwargs["text"] == "成功"


def test_result_omits_unknown_balance() -> None:
    """接口没有返回余额时，通知正文不应出现未知余额。"""
    result = TangRedPacketClaim._build_result("completed", "任务完成", 1, 44, None)

    assert result["message"] == "任务完成，本轮获得魔力值 44"
    assert "未知" not in result["message"]


def test_get_site_cookie_supports_root_domain_and_missing_site() -> None:
    """站点保存为根域名时也应读取成功，空对象不能触发属性异常。"""
    site_oper = sys.modules["app.db.oper.site"].SiteOper
    site_oper.return_value.get_by_domain.side_effect = [None, SimpleNamespace(cookie=" c_secure_pass=token ")]

    assert TangRedPacketClaim._get_site_cookie() == "c_secure_pass=token"
    assert site_oper.return_value.get_by_domain.call_args_list[0].args == ("www.tangpt.top",)
    assert site_oper.return_value.get_by_domain.call_args_list[1].args == ("tangpt.top",)


def test_claim_all_refreshes_until_list_is_empty() -> None:
    plugin = make_plugin()
    request = MagicMock()
    request.get_json.side_effect = [
        {"ok": True, "items": [{"id": 1, "remain_count": 1}], "total_packet_count": 2},
        {"ok": True, "items": [{"id": 2, "remain_count": 1}], "total_packet_count": 2},
        {"ok": True, "items": [], "total_packet_count": 2},
    ]
    response = MagicMock()
    response.json.side_effect = [
        {"ok": True, "magic_amount": 44, "user_bonus_after": 125088087},
        {"ok": True, "magic_amount": 56, "user_bonus_after": 125088143},
    ]
    request.post_res.return_value = response

    with patch("app.plugins.tangredpacketclaim.RequestUtils", return_value=request), patch(
        "app.plugins.tangredpacketclaim.time.sleep"
    ):
        result = plugin._claim_all("c_secure_pass=token")

    assert result["status"] == "completed"
    assert "2" in result["message"]
    assert result["magic_total"] == 100
    assert result["user_bonus_after"] == 125088143
    assert "本轮获得魔力值 100" in result["message"]
    assert "领取后魔力值 125088143" in result["message"]
    assert request.get_json.call_count == 3
    assert request.post_res.call_count == 2


def test_claim_all_stops_at_daily_limit() -> None:
    plugin = make_plugin()
    request = MagicMock()
    request.get_json.return_value = {"ok": True, "items": [{"id": 1, "remain_count": 1}]}
    response = MagicMock()
    response.json.return_value = {"ok": False, "message": "今天已经领取100个，每天最多领100个。"}
    request.post_res.return_value = response

    with patch("app.plugins.tangredpacketclaim.RequestUtils", return_value=request):
        result = plugin._claim_all("c_secure_pass=token")

    assert result["status"] == "limit_reached"
    assert result["magic_total"] == 0
