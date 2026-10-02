#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== 开始使用 Docker 构建 Android 安装包 ==="

cd "$PROJECT_ROOT"

# 创建挂载目录（放在 /home/tayhe 分区，有 78GB 充足空间，避开根目录空间不足）
mkdir -p "$PROJECT_ROOT/android/.gradle_home"
mkdir -p "$PROJECT_ROOT/android/.tmp"
chmod 777 "$PROJECT_ROOT/android/.gradle_home" "$PROJECT_ROOT/android/.tmp"

HOST_UID="$(id -u)"
HOST_GID="$(id -g)"

# 使用 mobiledevops/android-sdk-image 容器进行免环境编译
docker run --rm \
    --platform linux/amd64 \
    -u root \
    -v "$PROJECT_ROOT/android:/workspace" \
    -v "$PROJECT_ROOT/android/.gradle_home:/root/.gradle" \
    -v "$PROJECT_ROOT/android/.tmp:/tmp" \
    -e TMPDIR=/tmp \
    -w /workspace \
    mobiledevops/android-sdk-image:34.0.0-jdk17 \
    bash -c '
        set -e
        if [ ! -f "gradlew" ] || [ ! -f "gradle/wrapper/gradle-wrapper.jar" ]; then
            echo "--> 正在下载 Gradle 8.7 初始化 Wrapper..."
            curl -fSL "https://services.gradle.org/distributions/gradle-8.7-bin.zip" -o /tmp/gradle.zip
            unzip -q /tmp/gradle.zip -d /tmp
            /tmp/gradle-8.7/bin/gradle wrapper --gradle-version 8.7
            rm -rf /tmp/gradle.zip /tmp/gradle-8.7
        fi
        chmod +x gradlew
        echo "--> 开始编译 Release APK..."
        ./gradlew :app:assembleRelease --no-daemon --stacktrace
        chown -R '"$HOST_UID:$HOST_GID"' /workspace /root/.gradle /tmp || true
    '

OUTPUT_APK="$PROJECT_ROOT/android/app/build/outputs/apk/release/app-release-unsigned.apk"
if [ ! -f "$OUTPUT_APK" ]; then
    OUTPUT_APK="$PROJECT_ROOT/android/app/build/outputs/apk/release/app-release.apk"
fi

if [ -f "$OUTPUT_APK" ]; then
    FINAL_APK="$PROJECT_ROOT/android/habits-tracker.apk"
    cp "$OUTPUT_APK" "$FINAL_APK"
    echo "=========================================="
    echo "🎉 构建成功！"
    echo "安装包路径: $FINAL_APK"
    ls -lh "$FINAL_APK"
    echo "=========================================="
else
    echo "❌ 未找到生成的 APK 文件，请检查构建日志。"
    exit 1
fi
