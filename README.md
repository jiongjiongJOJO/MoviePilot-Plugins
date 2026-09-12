# MoviePilot 第三方插件仓库

本仓库用于维护 MoviePilot V3 第三方插件，采用与官方插件仓库一致的目录和市场索引结构。

## 目录

```text
plugins.v2/                 # V2 插件源码
plugins.v3/                 # V3 插件源码
tests/v2/                   # V2 插件测试
tests/v3/                   # V3 插件测试
package.v2.json             # V2 插件市场索引
package.v3.json             # V3 插件市场索引
```

## 插件

- `TangRedPacketClaim`：不可躺自动抢红包插件。V2 和 V3 分别位于
  `plugins.v2/tangredpacketclaim`、`plugins.v3/tangredpacketclaim`，Cookie 读取 MoviePilot
  站点管理中的 `www.tangpt.top` 记录，支持 Cron 定时执行和保存配置后立即执行一次。

插件开发约定和 V3 生命周期请参考 MoviePilot 官方插件开发指南。`docs/` 目录为开发时
临时参考资料，不属于本仓库的运行源码，后续可安全移除。

## 检查

```bash
python -m compileall plugins.v3/tangredpacketclaim tests/v3/tangredpacketclaim
python -m pytest tests/v3/tangredpacketclaim
git diff --check
```

## CI 与发布

- `.github/workflows/plugin-gate.yml`：在提交到 `main` 的 Pull Request 时执行官方版本、CSS 和测试门禁。
- `.github/workflows/release.yml`：在 `main` 分支的插件索引变化后，根据各代索引中 `release: true` 的条目创建 GitHub Release。
- Release 标签格式为 `<插件ID>_v<版本>`，例如 `TangRedPacketClaim_v0.0.1`。
- 发布压缩包格式为 `<插件目录>_v<版本>.zip`，例如 `tangredpacketclaim_v0.0.1.zip`。

GitHub Actions 默认使用仓库内置的 `GITHUB_TOKEN`，仓库设置需要允许 Actions 创建和写入 Releases。
