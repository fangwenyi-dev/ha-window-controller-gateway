"""诊断 MQTT 链路：验证消息是否能从 MQTT Broker 到达 HA 集成"""
import asyncio, json, sys, time
from datetime import datetime

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import aiomqtt
import aiohttp

MQTT_HOST = "192.168.1.91"
MQTT_PORT = 1883
MQTT_USER = "admin"
MQTT_PASS = "admin"

HA_URL = "http://100.66.70.121:8123"
HA_TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiIxYTdhN2FmNGUwODU0OGJjYmY5ZGZjZjE1MDc1YmI4MCIsImlhdCI6MTc3ODMxOTMyMCwiZXhwIjoyMDkzNjc5MzIwfQ.k0qSI7dJMKz7YxTvybjIjGquovsazGwJTTH8XfDl3Fk'

async def main():
    # 1. 连接到 MQTT Broker
    print(f"[1] 连接 MQTT {MQTT_HOST}:{MQTT_PORT} ...")
    mqtt = aiomqtt.Client(hostname=MQTT_HOST, port=MQTT_PORT,
                          username=MQTT_USER, password=MQTT_PASS,
                          identifier=f"diag_{int(time.time())}")
    await mqtt.__aenter__()
    print("  MQTT 已连接 ✅")

    # 2. 订阅 gateway/rsp 看看有没有消息
    await mqtt.subscribe("gateway/rsp")
    print(f"  已订阅 gateway/rsp")

    # 3. 通过 HA API 发布一条消息到 gateway/rsp
    print(f"\n[2] 通过 HA API 发布消息到 gateway/rsp ...")
    async with aiohttp.ClientSession(headers={
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json"
    }) as session:
        test_payload = {"head": "$SH", "ctype": "001", "id": 1,
                        "data": {"vesion": "1.0", "model": "诊断测试", "userid": "diag"},
                        "sn": "DIAG_TEST"}
        async with session.post(f"{HA_URL}/api/services/mqtt/publish", json={
            "topic": "gateway/rsp",
            "payload": json.dumps(test_payload, ensure_ascii=False),
            "qos": 1
        }, timeout=10) as resp:
            print(f"  HA API 发布: {resp.status}")
            if resp.status in (200, 201):
                result = await resp.json()
                print(f"  HA 响应: {json.dumps(result, ensure_ascii=False)[:100]}")

    # 4. 通过 MQTT 直接发布一条消息到 gateway/rsp
    print(f"\n[3] 通过 MQTT 直接发布消息到 gateway/rsp ...")
    direct_payload = {"head": "$SH", "ctype": "001", "id": 2,
                      "data": {"vesion": "1.0", "model": "直连测试", "userid": "direct"},
                      "sn": "DIRECT_TEST"}
    await mqtt.publish("gateway/rsp", json.dumps(direct_payload, ensure_ascii=False), qos=1)
    print("  MQTT 直接发布 ✅")

    # 5. 等待并检查是否能收到任何 gateway/rsp 消息
    print(f"\n[4] 等待 5 秒检查 gateway/rsp 消息...")
    msg_count = 0
    try:
        async with asyncio.timeout(5):
            async for msg in mqtt.messages:
                msg_count += 1
                topic = msg.topic.value if hasattr(msg.topic, 'value') else str(msg.topic)
                payload = json.loads(msg.payload)
                print(f"  收到 [{topic}]: ctype={payload.get('ctype','?')} sn={payload.get('sn','?')}")
                if msg_count >= 5:
                    break
    except (asyncio.TimeoutError, asyncio.CancelledError):
        pass
    print(f"  gateway/rsp 消息统计: {msg_count} 条")

    # 6. 检查 HA 中是否有我们的测试网关实体
    print(f"\n[5] 检查 HA 实体...")
    async with aiohttp.ClientSession(headers={
        "Authorization": f"Bearer {HA_TOKEN}",
        "Content-Type": "application/json"
    }) as session:
        async with session.get(f"{HA_URL}/api/states", timeout=15) as resp:
            if resp.status == 200:
                states = await resp.json()
                # 查找测试网关的实体
                diag_entities = [s for s in states if 'DIAG_TEST' in s['entity_id'] or 'DIRECT_TEST' in s['entity_id']]
                all_gateway = [s for s in states if '1001' in s['entity_id'] or '500' in s['entity_id']]
                kai_chuang = [s for s in states if 'kai_chuang' in s['entity_id']]
                print(f"  DIAG_TEST/DIRECT_TEST 实体: {len(diag_entities)}")
                print(f"  1001/500 网关实体: {len(all_gateway)}")
                print(f"  真实开窗器实体: {len(kai_chuang)}")

    # 7. 结论
    print(f"\n=== 诊断结论 ===")
    if msg_count > 0:
        print("gateway/rsp 上有活跃消息 → 集成可能正在接收 ✅")
    else:
        print("gateway/rsp 上无消息 → 集成可能未连接到此 Broker ❌")

    if all_gateway:
        print(f"网关实体已存在: {all_gateway[:3]}... ✅")
    else:
        print("无网关实体 → 集成未处理此 Broker 上的消息 ❌")

    await mqtt.__aexit__(None, None, None)
    print("MQTT 已断开")

asyncio.run(main())