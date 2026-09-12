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


def test_claim_all_refreshes_until_list_is_empty() -> None:
    plugin = make_plugin()
    request = MagicMock()
    request.get_json.side_effect = [
        {"ok": True, "items": [{"id": 1, "remain_count": 1}], "total_packet_count": 2},
        {"ok": True, "items": [{"id": 2, "remain_count": 1}], "total_packet_count": 2},
        {"ok": True, "items": [], "total_packet_count": 2},
    ]
    response = MagicMock()
    response.json.return_value = {"ok": True}
    request.post_res.return_value = response

    with patch("app.plugins.tangredpacketclaim.RequestUtils", return_value=request), patch(
        "app.plugins.tangredpacketclaim.time.sleep"
    ):
        result = plugin._claim_all("c_secure_pass=token")

    assert result["status"] == "completed"
    assert "2" in result["message"]
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
