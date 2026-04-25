"""
设备LLM服务测试脚本
测试设备识别功能

使用方式：
    python test_device_server.py
"""

import asyncio
import aiohttp
import json
from typing import List, Dict, Any

# 服务地址（已改为12345端口）
API_URL = "http://127.0.0.1:12345/api/classify"
HEALTH_URL = "http://127.0.0.1:12345/health"
DEEP_HEALTH_URL = "http://127.0.0.1:12345/health/deep"

# 测试用例
TEST_CASES = [
    # (输入, 预期设备, 说明)
    ("打开空调", ["空调"], "只有空调"),
    ("打开灯", ["灯光"], "只有灯光"),
    ("打开电脑", ["电脑"], "只有电脑"),
    ("打开空调和灯", ["灯光", "空调"], "空调和灯"),
    ("关掉空调", ["空调"], "关空调也是空调相关"),
    ("房间太黑，打开所有的灯", ["灯光"], "只有灯光"),
    ("打开房屋里的电脑并进入汇报模式", ["电脑"], "电脑汇报模式"),
    ("天气太热，需要打开空调，同时打开卧室的灯", ["灯光", "空调"], "复杂句子"),
    ("今天天气很好", [], "无设备"),
    ("冷气坏了", ["空调"], "冷气=空调"),
    ("照明不足", ["灯光"], "照明=灯光"),
    ("我想控制温度和亮度", ["灯光", "空调"], "温度+亮度"),
    ("请把电脑打开、灯调亮、空调调到24度", ["电脑", "灯光", "空调"], "三设备联动"),
]


async def health_check() -> bool:
    """检查服务健康状态"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(HEALTH_URL, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"✓ 健康检查成功")
                    print(f"  状态: {data.get('status')}")
                    print(f"  端口: {data.get('port')}")
                    print(f"  模型API: {data.get('llm_api')}")
                else:
                    print(f"✗ 健康检查失败: HTTP {resp.status}")
                    return False

            async with session.get(DEEP_HEALTH_URL, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    print(f"✗ 深度健康检查失败: HTTP {resp.status}")
                    return False

                data = await resp.json()
                checks = data.get("checks", {})
                llm_api = checks.get("llm_api", {})
                digital_twin = checks.get("digital_twin", {})
                print("✓ 深度健康检查成功")
                print(f"  总体状态: {data.get('status')}")
                print(f"  LLM连通: {llm_api.get('ok')}  延迟: {llm_api.get('latency_ms')} ms")
                print(f"  Twin连通: {digital_twin.get('ok')}  延迟: {digital_twin.get('latency_ms')} ms")
                twin_required = bool(digital_twin.get("enabled"))
                return bool(llm_api.get("ok")) and (not twin_required or bool(digital_twin.get("ok")))
    except Exception as e:
        print(f"✗ 无法连接到服务: {e}")
        return False


async def test_classification(input_text: str, expected_devices: List[str]) -> Dict[str, Any]:
    """
    测试设备分类
    
    Args:
        input_text: 输入文本
        expected_devices: 预期的设备列表
    
    Returns:
        测试结果
    """
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                API_URL,
                json={"input": input_text},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    # 检查结果
                    devices = data.get('devices', [])
                    success = data.get('success', False)
                    
                    # 验证预期设备
                    match = set(devices) == set(expected_devices)
                    
                    return {
                        "input": input_text,
                        "success": success,
                        "devices": devices,
                        "expected": expected_devices,
                        "match": match,
                        "analysis": data.get('analysis', '')[:120],
                        "plans": data.get('plans', []),
                    }
                else:
                    error_text = await resp.text()
                    return {
                        "input": input_text,
                        "success": False,
                        "error": f"HTTP {resp.status}: {error_text}",
                        "devices": [],
                        "expected": expected_devices,
                        "match": False
                    }
    
    except asyncio.TimeoutError:
        return {
            "input": input_text,
            "success": False,
            "error": "请求超时 (30秒)",
            "devices": [],
            "expected": expected_devices,
            "match": False
        }
    except Exception as e:
        return {
            "input": input_text,
            "success": False,
            "error": str(e),
            "devices": [],
            "expected": expected_devices,
            "match": False
        }


async def run_tests():
    """运行所有测试"""
    print("=" * 70)
    print("设备LLM服务测试套件")
    print("=" * 70)
    print()
    
    # 1. 健康检查
    print("【步骤1】健康检查")
    print("-" * 70)
    is_healthy = await health_check()
    print()
    
    if not is_healthy:
        print("⚠️  服务不可用，无法继续测试")
        print("请确保:")
        print("  1. 外部LLM API正在运行 (http://127.0.0.1:48760)")
        print("  2. device_llm_server正在运行 (python device_llm_server.py)")
        return
    
    # 2. 功能测试
    print("【步骤2】功能测试")
    print("-" * 70)
    
    passed = 0
    failed = 0
    
    for i, (input_text, expected, description) in enumerate(TEST_CASES, 1):
        print(f"\n测试{i}: {description}")
        print(f"输入: {input_text}")
        print(f"预期: {expected}")
        
        result = await test_classification(input_text, expected)
        
        if result['success'] and result['match']:
            print(f"✓ 通过 - 识别到: {result['devices']}")
            passed += 1
        else:
            print(f"✗ 失败")
            if not result['success']:
                print(f"  错误: {result.get('error', '未知错误')}")
            else:
                print(f"  识别到: {result['devices']}")
            failed += 1
        
        # 显示LLM分析（如有）
        if result.get('analysis'):
            print(f"  分析: {result['analysis']}...")
        if result.get('plans'):
            summaries = [f"{plan.get('label')}->{plan.get('intent')}" for plan in result['plans']]
            print(f"  方案: {summaries}")
    
    # 3. 测试总结
    print()
    print("=" * 70)
    print("测试总结")
    print("=" * 70)
    print(f"总计: {len(TEST_CASES)} 个测试")
    print(f"通过: {passed} ✓")
    print(f"失败: {failed} ✗")
    
    if failed == 0:
        print("\n🎉 所有测试通过！")
    else:
        print(f"\n⚠️  有 {failed} 个测试失败")
    
    print("=" * 70)


async def main():
    """主函数"""
    try:
        await run_tests()
    except KeyboardInterrupt:
        print("\n\n用户中断，测试停止")
    except Exception as e:
        print(f"\n✗ 测试异常: {e}")


if __name__ == "__main__":
    asyncio.run(main())
