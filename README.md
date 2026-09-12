# MoviePilot 第三方 V3 插件仓库

本仓库用于维护 MoviePilot V3 第三方插件，采用与官方插件仓库一致的目录和市场索引结构。

## 目录

```text
plugins.v3/                 # V3 插件源码
tests/v3/                   # V3 插件测试
package.v3.json             # V3 插件市场索引
```

## 插件

- `TangRedPacketClaim`：不可躺自动抢红包插件。Cookie 读取 MoviePilot 站点管理中的
  `www.tangpt.top` 记录，支持 Cron 定时执行和保存配置后立即执行一次。

插件开发约定和 V3 生命周期请参考 MoviePilot 官方插件开发指南。`docs/` 目录为开发时
临时参考资料，不属于本仓库的运行源码，后续可安全移除。

## 检查

```bash
python -m compileall plugins.v3/tangredpacketclaim tests/v3/tangredpacketclaim
python -m pytest tests/v3/tangredpacketclaim
git diff --check
```
