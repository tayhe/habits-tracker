# 小鱼干打卡 · 安卓平板客户端

本目录包含「小鱼干·学习习惯追踪」专用的 Android 平板客户端源码（WebView 原生壳）。

## 平板专属特性

1. **沉浸式全屏**：隐藏系统顶部状态栏和底部导航栏，获得最大显示面积，边缘滑动可呼出系统条。
2. **屏幕常亮（Keep Screen On）**：开启后平板不休眠，适合做作业、学习期间立在书桌上实时查看任务进度。
3. **儿童防误触**：连续快速按两次返回键才会退出应用，防止小朋友打卡过程中误触手势退出。
4. **异常友好兜底**：网络断开或服务器波动时，展示友好的断网提示卡片，支持一键「重新加载」与「修改网址」。
5. **隐形设置入口**：
   - 断网页面直接提供「修改网址」按钮。
   - 正常浏览时，**快速点击屏幕右上角 3 次**，即可唤起服务器网址与屏幕常亮配置弹窗（防小朋友误触，方便家长修改）。
6. **独立会话沙盒**：基于 Android 原生 `CookieManager` 管理 Session Cookie，与平板浏览器完全隔离。
7. **咚咚鼠原生图标**：自动从 `frontend/assets/dedenne.png` 生成全分辨率高清 App 图标。

---

## 构建与发布规范（严禁本地编译）

> [!IMPORTANT]
> **【核心规范】本项目严禁在本地电脑进行 Android APK 编译。**
> 
> - **原因**：本地编译需要拉取数 GB 的 Docker 镜像或安装庞大的 Android SDK / Gradle 依赖环境，容易导致本地磁盘空间暴增（仅 Gradle 缓存即可占用 1GB+）。
> - **规范**：所有 APK 构建工作统一交由 **GitHub Actions 云端全自动完成**，云端虚拟机天然内置最新 Android SDK 与 JDK 17，2 分钟内即可完成打包与产物归档。

### 获取最新 APK 安装包

#### 1. 网页端下载
1. 打开项目的 GitHub 仓库页面，点击顶部导航栏的 **Actions**。
2. 在左侧选择 **Build Android APK** 工作流。
3. 点击最近一次成功运行（绿勾 ✓）的记录。
4. 滑动至页面最下方的 **Artifacts** 区域，点击 **habits-tracker-apk** 下载压缩包，解压后即为 `app-release.apk`。

#### 2. 命令行下载（GitHub CLI）
```bash
# 查看最近一次构建
gh run list --workflow=android.yml --limit 1

# 直接下载最新构建产物到当前目录
gh run download --name habits-tracker-apk
```

### 触发构建规则

- **自动触发**：向 `main` 分支推送任何涉及 `android/**` 目录的代码或提交相关 Pull Request 时，GitHub 会自动触发编译。
- **手动触发**：
  - **网页端**：在 Actions 页面选择 **Build Android APK** -> 点击 **Run workflow** -> 确认运行。
  - **CLI 端**：在终端执行 `gh workflow run android.yml`。

---

## 本地代码修改与调试

如需对 Android 原生壳功能进行代码调整（如修改 `MainActivity.kt` 或配置项）：
1. 直接在本地编辑 `android/` 下的源码或使用 Android Studio 查看与编写代码。
2. **切勿在本地执行任何编译脚本或构建命令**。
3. 修改完成后提交并推送到 GitHub，由 GitHub Actions 负责编译并验证 APK。
