"""
scripts/test_tts_smoke.py - 火山引擎 TTS 单段冒烟测试

用途：用户开通火山引擎"语音技术→语音合成"服务并配置 .env 后，
      先跑这个脚本验证 API 字段/鉴权/返回解析是否正确，再进入批量生成。

用法：
    python scripts/test_tts_smoke.py
    python scripts/test_tts_smoke.py --text "变量是存储数据的容器" --voice zh_female_wanwanxiaohe_moon_bigtts
    python scripts/test_tts_smoke.py --cluster volcano_tts   # 普通双向流式音色用这个 cluster

验证项：
    1. 鉴权通过（app_id + access_token 正确）
    2. 返回 base64 能解码成可播放 mp3
    3. word_timestamps 非空（逐字时间戳）
    4. duration_ms 合理（与文本长度匹配）
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys
from pathlib import Path

# 项目根目录加入 sys.path（脚本在 scripts/ 子目录）
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()  # 加载 .env

from utils.tts_api import tts_client, TTSAPIError
from config.model_config import TTS_CONFIG


DEFAULT_TEXT = "欢迎学习 Python 编程，今天我们来理解变量这个核心概念。变量就像一个带标签的盒子，用来存储数据。"


async def main(text: str, voice_id: str, cluster: str | None) -> int:
    print("=" * 60)
    print("🎤 火山引擎 TTS 单段冒烟测试")
    print("=" * 60)

    # 1. 检查配置
    print(f"\n📍 配置检查:")
    print(f"  TTS_ENABLED     = {TTS_CONFIG.enabled}")
    print(f"  TTS_APP_ID      = {TTS_CONFIG.app_id[:8]}{'***' if TTS_CONFIG.app_id else '(未配置)'}")
    print(f"  TTS_ACCESS_TOKEN= {TTS_CONFIG.access_token[:8]}{'***' if TTS_CONFIG.access_token else '(未配置)'}")
    print(f"  default_voice   = {TTS_CONFIG.default_voice_id}")
    print(f"  api_endpoint    = {TTS_CONFIG.api_endpoint}")
    if cluster:
        print(f"  cluster override= {cluster}")

    if not tts_client.is_enabled():
        print("\n❌ TTS 未启用或凭证未配置")
        print("   请检查 .env 文件：")
        print("   TTS_ENABLED=true")
        print("   TTS_APP_ID=你的AppID")
        print("   TTS_ACCESS_TOKEN=你的AccessToken")
        return 1

    # 2. 调用合成
    voice = voice_id or TTS_CONFIG.default_voice_id
    print(f"\n📤 合成请求:")
    print(f"  text    = {text}")
    print(f"  voice   = {voice}")
    print(f"  cluster = {cluster or tts_client.DEFAULT_CLUSTER}")

    # 临时覆盖 cluster（如果用户指定）
    original_cluster = tts_client.DEFAULT_CLUSTER
    if cluster:
        tts_client.DEFAULT_CLUSTER = cluster

    try:
        result = await tts_client.synthesize(text, voice_id=voice)
    except TTSAPIError as e:
        print(f"\n❌ 合成失败: {type(e).__name__}: {e}")
        print("\n💡 排查建议:")
        if "鉴权" in str(e) or "401" in str(e) or "3001" in str(e):
            print("   - 检查 TTS_APP_ID/TTS_ACCESS_TOKEN 是否正确")
            print("   - 确认已在火山引擎控制台开通'语音合成'服务（非方舟 LLM）")
            print("   - 确认 access_token 未过期")
        if "3003" in str(e) or "429" in str(e):
            print("   - 限流，稍后重试")
        if "cluster" in str(e).lower() or "voice" in str(e).lower():
            print("   - BigModel 音色用 cluster=volcano_mega（默认）")
            print("   - 普通双向流式音色用 cluster=volcano_tts，加参数 --cluster volcano_tts")
            print("   - 确认 voice_id 与 cluster 匹配（_bigtts 后缀的音色属 BigModel）")
        return 2
    finally:
        if cluster:
            tts_client.DEFAULT_CLUSTER = original_cluster

    # 3. 验证返回
    print(f"\n✅ 合成成功:")
    print(f"  audio_b64_len   = {len(result.audio_b64)} 字符")
    print(f"  duration_ms     = {result.duration_ms} ms ({result.duration_ms/1000:.2f}s)")
    print(f"  word_timestamps = {len(result.word_timestamps)} 项")

    if result.word_timestamps:
        print(f"\n📊 前 5 个时间戳:")
        for i, ts in enumerate(result.word_timestamps[:5]):
            print(f"  [{i}] text={ts.get('text', '?')!r} start_ms={ts.get('start_ms', '?')} duration_ms={ts.get('duration_ms', '?')}")

    # 4. 保存 mp3 文件供人工播放验证
    output_dir = Path("static/videos/audio")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"smoke_test_{voice[:20]}.mp3"
    output_file.write_bytes(base64.b64decode(result.audio_b64))
    print(f"\n💾 音频已保存: {output_file.resolve()}")
    print(f"   大小: {output_file.stat().st_size / 1024:.1f} KB")
    print(f"   请用播放器打开听效果，确认音质和自然度")

    # 5. 合理性校验
    print(f"\n🔍 合理性校验:")
    issues = []
    if not result.audio_b64:
        issues.append("audio_b64 为空")
    if result.duration_ms <= 0:
        issues.append("duration_ms <= 0")
    if result.duration_ms > 0:
        # 中文约 4-5 字/秒，校验时长与字数比例
        char_count = len(text)
        expected_sec = char_count / 4.5
        actual_sec = result.duration_ms / 1000
        ratio = actual_sec / expected_sec if expected_sec > 0 else 0
        print(f"  文本字数={char_count}, 估算时长={expected_sec:.1f}s, 实际时长={actual_sec:.1f}s, 比例={ratio:.2f}")
        if ratio < 0.3 or ratio > 3.0:
            issues.append(f"时长比例异常（{ratio:.2f}），可能 duration 字段单位或解析有误")

    if not result.word_timestamps:
        print(f"  ⚠️ word_timestamps 为空（with_timestamp 可能未生效，前端会回退整段字幕）")
    else:
        print(f"  ✅ word_timestamps 非空，前端可逐字高亮")

    if issues:
        print(f"\n⚠️ 发现问题:")
        for iss in issues:
            print(f"  - {iss}")
        print("\n💡 请核对火山引擎官方文档字段定义，修正 utils/tts_api.py 的 _handle_business_error 和返回解析")
        return 3

    print(f"\n{'='*60}")
    print(f"✅ 冒烟测试通过！可以进入批量生成阶段。")
    print(f"{'='*60}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="火山引擎 TTS 单段冒烟测试")
    parser.add_argument("--text", default=DEFAULT_TEXT, help="测试文本")
    parser.add_argument("--voice", default=None, help="音色 ID（默认用 TTS_DEFAULT_VOICE_ID）")
    parser.add_argument("--cluster", default=None, help="集群（volcano_mega 或 volcano_tts，默认 volcano_mega）")
    args = parser.parse_args()

    exit_code = asyncio.run(main(args.text, args.voice, args.cluster))
    sys.exit(exit_code)
