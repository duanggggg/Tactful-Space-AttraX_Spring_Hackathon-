#!/usr/bin/env python
"""
MCP LLM集成 - 实际使用示例
演示如何在实际应用中使用MCP LLM Agent
"""

import asyncio
import logging
from typing import Optional

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 示例1: 直接使用LLMClient
# ============================================================================

async def example_1_direct_llm_client():
    """直接使用LLM客户端进行查询"""
    logger.info("=" * 60)
    logger.info("示例1: 直接使用LLMClient")
    logger.info("=" * 60)
    
    from llm_agent import LLMClient
    
    client = LLMClient(base_url="http://localhost:12345", timeout=30)
    
    try:
        # 检查健康状态
        is_healthy = await client.health_check()
        logger.info(f"LLM服务健康状态: {is_healthy}")
        
        if not is_healthy:
            logger.warning("LLM服务可能不可用")
            return
        
        # Chat模式
        logger.info("\n--- Chat模式 ---")
        response = await client.chat([
            {"role": "system", "content": "你是一个有帮助的AI助手"},
            {"role": "user", "content": "请解释什么是MCP协议"}
        ])
        logger.info(f"Chat响应: {response[:200]}...")
        
        # Completion模式
        logger.info("\n--- Completion模式 ---")
        response = await client.completion("Python的def关键字用于定义")
        logger.info(f"Completion响应: {response[:200]}...")
        
    finally:
        await client.close()


# 示例2: MCP工具的异步调用
# ============================================================================

async def example_2_mcp_tools():
    """通过异步调用MCP工具"""
    logger.info("=" * 60)
    logger.info("示例2: 异步调用MCP工具")
    logger.info("=" * 60)
    
    from llm_agent import ask_llm, ask_llm_with_context, llm_code_completion
    
    # 工具1: 基础ask_llm
    logger.info("\n--- ask_llm工具 ---")
    result = await ask_llm(
        question="什么是函数式编程？",
        chat_mode="chat"
    )
    if result["success"]:
        logger.info(f"问题: {result['question']}")
        logger.info(f"回答: {result['response'][:200]}...")
    else:
        logger.error(f"错误: {result.get('error')}")
    
    # 工具2: ask_llm_with_context
    logger.info("\n--- ask_llm_with_context工具 ---")
    result = await ask_llm_with_context(
        question="如何改进这个函数？",
        context="def slow_function(items):\n    for item in items:\n        time.sleep(1)\n        process(item)",
        chat_mode="chat"
    )
    if result["success"]:
        logger.info(f"问题: {result['question']}")
        logger.info(f"上下文: {result['context'][:50]}...")
        logger.info(f"建议: {result['response'][:200]}...")
    
    # 工具3: 代码补全
    logger.info("\n--- llm_code_completion工具 ---")
    result = await llm_code_completion(
        code_prefix="def factorial(n):\n    if n <= 1:\n        return 1\n    return"
    )
    if result["success"]:
        logger.info(f"输入: {result['prefix'][:50]}...")
        logger.info(f"补全: {result['completion'][:200]}...")


# 示例3: 模拟MCP服务器场景
# ============================================================================

async def example_3_mcp_server_scenario():
    """模拟MCP服务器接收指令并转发到LLM"""
    logger.info("=" * 60)
    logger.info("示例3: MCP服务器场景")
    logger.info("=" * 60)
    
    from llm_agent import ask_llm, llm_analyze_instruction
    
    # 模拟MCP接收到的指令序列
    mcp_instructions = [
        "用户询问如何学习Python",
        "用户询问如何优化代码性能",
        "用户询问如何调试程序"
    ]
    
    for instruction in mcp_instructions:
        logger.info(f"\nMCP接收到指令: {instruction}")
        
        # 分析指令
        analysis = await llm_analyze_instruction(instruction)
        
        if analysis["success"]:
            logger.info(f"指令分析:\n{analysis['analysis'][:300]}...")
        else:
            logger.error(f"分析失败: {analysis.get('error')}")


# 示例4: 错误处理和重试
# ============================================================================

async def example_4_error_handling():
    """演示错误处理和重试机制"""
    logger.info("=" * 60)
    logger.info("示例4: 错误处理和重试")
    logger.info("=" * 60)
    
    from llm_agent import LLMClient
    
    client = LLMClient(base_url="http://localhost:12345", timeout=5)
    
    # 重试逻辑
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            is_healthy = await client.health_check()
            if not is_healthy:
                raise ConnectionError("LLM服务不可用")
            
            # 发送查询
            response = await client.chat([
                {"role": "user", "content": "Test message"}
            ])
            logger.info(f"成功获得响应: {response[:100]}...")
            break
            
        except (ConnectionError, asyncio.TimeoutError) as e:
            retry_count += 1
            logger.warning(f"尝试#{retry_count}失败: {e}")
            
            if retry_count < max_retries:
                wait_time = 2 ** retry_count  # 指数退避
                logger.info(f"等待{wait_time}秒后重试...")
                await asyncio.sleep(wait_time)
            else:
                logger.error("达到最大重试次数，放弃")
        
        except Exception as e:
            logger.error(f"未预期的错误: {e}")
            break
    
        finally:
            await client.close()


# 示例5: 批量处理多个请求
# ============================================================================

async def example_5_batch_processing():
    """批量处理多个请求"""
    logger.info("=" * 60)
    logger.info("示例5: 批量处理请求")
    logger.info("=" * 60)
    
    from llm_agent import ask_llm
    
    # 定义多个问题
    questions = [
        "什么是递归？",
        "什么是动态规划？",
        "什么是贪心算法？",
        "什么是分治算法？"
    ]
    
    # 并发处理所有问题
    logger.info(f"开始处理{len(questions)}个问题...")
    
    tasks = [
        ask_llm(question, chat_mode="chat")
        for question in questions
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 处理结果
    for i, (question, result) in enumerate(zip(questions, results), 1):
        logger.info(f"\n问题{i}: {question}")
        
        if isinstance(result, Exception):
            logger.error(f"错误: {result}")
        elif isinstance(result, dict) and result.get("success"):
            logger.info(f"回答: {result['response'][:150]}...")
        else:
            logger.error(f"处理失败: {result}")


# 示例6: 集成计算器和LLM
# ============================================================================

async def example_6_integrated_workflow():
    """演示计算器和LLM工具的集成工作流"""
    logger.info("=" * 60)
    logger.info("示例6: 集成工作流 (计算 + LLM解释)")
    logger.info("=" * 60)
    
    from llm_agent import ask_llm_with_context
    
    # 步骤1: 进行计算 (通常通过calculator工具)
    # 这里模拟计算结果
    calculation = "sqrt(16) = 4"
    logger.info(f"步骤1 - 执行计算: {calculation}")
    
    # 步骤2: 使用LLM解释结果
    logger.info(f"步骤2 - LLM解释计算结果")
    
    result = await ask_llm_with_context(
        question="这个计算结果说明了什么？",
        context=f"计算: {calculation}",
        chat_mode="chat"
    )
    
    if result["success"]:
        logger.info(f"解释: {result['response'][:300]}...")


# 示例7: 自定义LLM客户端参数
# ============================================================================

async def example_7_custom_client_params():
    """使用自定义参数创建LLM客户端"""
    logger.info("=" * 60)
    logger.info("示例7: 自定义客户端参数")
    logger.info("=" * 60)
    
    from llm_agent import LLMClient
    
    # 创建具有自定义参数的客户端
    client = LLMClient(
        base_url="http://localhost:12345",  # 自定义URL
        timeout=60  # 自定义超时
    )
    
    try:
        # 进行查询并观察参数效果
        response = await client.chat(
            [{"role": "user", "content": "Write a poem about AI"}],
            model="default",  # 自定义模型
            temperature=0.9  # 自定义温度 (更创意)
        )
        logger.info(f"高创意模式响应:\n{response[:300]}...")
        
        # 低温度 (更确定)
        response = await client.chat(
            [{"role": "user", "content": "What is 2+2?"}],
            temperature=0.1
        )
        logger.info(f"低温度模式响应:\n{response}")
        
    finally:
        await client.close()


# 主函数
# ============================================================================

async def main():
    """运行所有示例"""
    logger.info("\n" + "=" * 60)
    logger.info("MCP LLM Assistant 集成示例")
    logger.info("=" * 60)
    logger.info("说明: 确保本地LLM服务运行在 localhost:12345\n")
    
    # 选择要运行的示例
    examples = [
        ("1", "直接使用LLMClient", example_1_direct_llm_client),
        ("2", "异步调用MCP工具", example_2_mcp_tools),
        ("3", "MCP服务器场景", example_3_mcp_server_scenario),
        ("4", "错误处理和重试", example_4_error_handling),
        ("5", "批量处理请求", example_5_batch_processing),
        ("6", "集成工作流", example_6_integrated_workflow),
        ("7", "自定义客户端参数", example_7_custom_client_params),
    ]
    
    logger.info("可用的示例:")
    for num, name, _ in examples:
        logger.info(f"  {num}. {name}")
    logger.info("  0. 运行所有示例")
    logger.info()
    
    # 注意：在实际使用中，应该从命令行获取用户输入
    # 这里为了演示，我们运行第一个示例
    
    try:
        # 运行示例1 (最基础的)
        await example_1_direct_llm_client()
        
        # 取消注释以运行其他示例
        # await example_2_mcp_tools()
        # await example_3_mcp_server_scenario()
        # await example_4_error_handling()
        # await example_5_batch_processing()
        # await example_6_integrated_workflow()
        # await example_7_custom_client_params()
        
    except KeyboardInterrupt:
        logger.info("用户中断")
    except Exception as e:
        logger.error(f"示例执行失败: {e}", exc_info=True)


if __name__ == "__main__":
    # 对于Windows系统，配置事件循环
    import sys
    if sys.platform == 'win32':
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    
    # 运行主函数
    asyncio.run(main())
