"""使用示例：演示如何使用智能出行规划助手API"""
import asyncio
import httpx
import json


async def example_travel_planning():
    """示例：完整的出行规划流程"""
    base_url = "http://localhost:8000/api/v1"
    user_id = "example_user_001"
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        # 第一步：初始请求（信息不完整）
        print("=" * 60)
        print("第一步：发送初始请求")
        print("=" * 60)
        
        response1 = await client.post(
            f"{base_url}/plan",
            json={
                "user_id": user_id,
                "user_input": "我想去上海旅游"
            }
        )
        result1 = response1.json()
        print(f"响应：{json.dumps(result1, ensure_ascii=False, indent=2)}")
        print()
        
        # 第二步：补充信息
        if not result1.get("success") or result1.get("missing_slots"):
            print("=" * 60)
            print("第二步：补充缺失信息")
            print("=" * 60)
            
            response2 = await client.post(
                f"{base_url}/plan",
                json={
                    "user_id": user_id,
                    "user_input": "从北京出发，1月15日，2个人，住五星级酒店"
                }
            )
            result2 = response2.json()
            print(f"响应：{json.dumps(result2, ensure_ascii=False, indent=2)}")
            print()
        
        # 第三步：查看最终规划
        if result2.get("success") and result2.get("plan_output"):
            print("=" * 60)
            print("最终规划方案：")
            print("=" * 60)
            print(result2["plan_output"])
            print()
        
        # 查看用户状态
        print("=" * 60)
        print("查看用户状态")
        print("=" * 60)
        response_state = await client.get(f"{base_url}/state/{user_id}")
        state = response_state.json()
        print(f"状态：{json.dumps(state, ensure_ascii=False, indent=2)}")
        print()
        
        # 清除状态（可选）
        # response_clear = await client.delete(f"{base_url}/state/{user_id}")
        # print(f"清除状态：{response_clear.json()}")


async def example_with_dynamic_instructions():
    """示例：使用动态指令"""
    base_url = "http://localhost:8000/api/v1"
    user_id = "example_user_002"
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{base_url}/plan",
            json={
                "user_id": user_id,
                "user_input": "从北京到上海，1月15日出发，2个人",
                "dynamic_instructions": {
                    "train_query": {
                        "seat_type": "二等座"  # 动态插入的指令
                    }
                }
            }
        )
        result = response.json()
        print(f"带动态指令的响应：{json.dumps(result, ensure_ascii=False, indent=2)}")


if __name__ == "__main__":
    print("智能出行规划助手 - API使用示例")
    print("=" * 60)
    print()
    
    # 运行示例
    asyncio.run(example_travel_planning())
    
    # 取消注释以运行动态指令示例
    # asyncio.run(example_with_dynamic_instructions())

