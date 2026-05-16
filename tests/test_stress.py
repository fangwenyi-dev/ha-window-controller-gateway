"""慧尖开窗器网关 - 优化版压力测试
直接连接 MQTT 192.168.1.91:1883
实时监听 gateway/rsp + 逐阶段 HA API 验证
"""
import asyncio, json, time, logging, os, random, sys
from datetime import datetime
from dataclasses import dataclass, field, asdict

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import aiomqtt, aiohttp

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
_LOGGER = logging.getLogger("stress_test")

MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASS = "192.168.1.91", 1883, "admin", "admin"
HA_URL, HA_TOKEN = "http://100.66.70.121:8123", 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiIxYTdhN2FmNGUwODU0OGJjYmY5ZGZjZjE1MDc1YmI4MCIsImlhdCI6MTc3ODMxOTMyMCwiZXhwIjoyMDkzNjc5MzIwfQ.k0qSI7dJMKz7YxTvybjIjGquovsazGwJTTH8XfDl3Fk'
GATEWAY_COUNT, DEVICES_PER_GATEWAY = 50, 10
GATEWAY_PREFIX, DEVICE_PREFIX = "1001", "500"
PROTOCOL_HEAD = "$SH"
TOPIC_RSP = "gateway/rsp"
TOPIC_REQ = "gateway/+/req"

@dataclass
class PhaseResult:
    name: str; success: bool = False; duration_ms: float = 0; errors: int = 0; detail: str = ""

@dataclass
class TestReport:
    total_gateways: int; total_devices: int
    phases: dict = field(default_factory=dict)
    overall_passed: bool = False; total_duration_ms: float = 0; total_errors: int = 0
    device_registration_rate: str = "0%"
    entities_before: int = 0; entities_after: int = 0
    mqtt_sent: int = 0; mqtt_received_on_rsp: int = 0; ha_commands: int = 0

class StressTest:
    def __init__(self):
        self.report = TestReport(GATEWAY_COUNT, GATEWAY_COUNT * DEVICES_PER_GATEWAY)
        self._mqtt = None; self._session = None
        self._errors = 0; self._start_time = 0; self._cmd_id = 0
        self._entities_before = set(); self._entities_after = set()
        self._mqtt_sent = 0; self._rsp_messages = []; self._ha_cmds = []
        self._stop_listener = False

    async def _connect(self):
        self._mqtt = aiomqtt.Client(hostname=MQTT_HOST, port=MQTT_PORT, username=MQTT_USER, password=MQTT_PASS, identifier=f"stress_{int(time.time())}")
        await self._mqtt.__aenter__()
        _LOGGER.info("MQTT %s:%s 已连接", MQTT_HOST, MQTT_PORT)
        self._session = aiohttp.ClientSession(headers={"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"})
        _LOGGER.info("HA API %s 已连接", HA_URL)

    async def _ha_get(self, p):
        async with self._session.get(f"{HA_URL}/api/{p.lstrip('/')}", timeout=15) as r:
            return await r.json() if r.status == 200 else {}

    async def _ha_post(self, p, d=None):
        async with self._session.post(f"{HA_URL}/api/{p.lstrip('/')}", json=d or {}, timeout=15) as r:
            return await r.json() if r.status in (200, 201) else {}

    async def _get_entity_ids(self):
        e = await self._ha_get("states")
        return {x["entity_id"] for x in e} if isinstance(e, list) else set()

    async def _publish(self, payload: dict):
        await self._mqtt.publish(TOPIC_RSP, json.dumps(payload, ensure_ascii=False), qos=1)
        self._mqtt_sent += 1

    def _next_id(self):
        self._cmd_id += 1; return self._cmd_id if self._cmd_id <= 65535 else 1

    def _make(self, ctype, data, sn):
        return {"head": PROTOCOL_HEAD, "ctype": ctype, "id": self._next_id(), "data": data, "sn": sn}

    async def _listen_rsp(self):
        """监听 gateway/rsp 上的所有消息"""
        await self._mqtt.subscribe(TOPIC_RSP)
        _LOGGER.info("已订阅 %s，开始监听", TOPIC_RSP)
        async for msg in self._mqtt.messages:
            if self._stop_listener: break
            try:
                p = json.loads(msg.payload)
                self._rsp_messages.append(p)
                if len(self._rsp_messages) <= 3:
                    _LOGGER.info("  [rsp] ctype=%s sn=%s", p.get("ctype","?"), p.get("sn","?"))
            except: pass

    async def _listen_req(self):
        """监听 HA 发往网关的命令"""
        await self._mqtt.subscribe(TOPIC_REQ)
        async for msg in self._mqtt.messages:
            if self._stop_listener: break
            try:
                p = json.loads(msg.payload)
                self._ha_cmds.append(p)
                _LOGGER.info("  [HA命令] ctype=%s sn=%s data=%s", p.get("ctype","?"), p.get("sn","?"), json.dumps(p.get("data",{}), ensure_ascii=False)[:80])
            except: pass

    def _log_phase(self, name):
        _LOGGER.info(""); _LOGGER.info("="*60); _LOGGER.info("阶段: %s", name); _LOGGER.info("="*60)

    async def _run_phase(self, name, coro):
        _LOGGER.info("[阶段] %s ...", name)
        start = time.time(); err_before = self._errors; detail = ""
        try: detail = await coro; ok = True
        except Exception as e: _LOGGER.error("阶段 %s 失败: %s", name, e); ok = False; self._errors += 1; detail = str(e)
        dur = (time.time()-start)*1000
        r = PhaseResult(name=name, success=ok, duration_ms=round(dur,1), errors=self._errors-err_before, detail=detail)
        self.report.phases[name] = r
        _LOGGER.info("[阶段] %s -> %s (%.0fms, %d errors)", name, "OK" if ok else "FAIL", dur, r.errors)
        return r

    async def _check_entities(self, label=""):
        entities = await self._get_entity_ids()
        kc = [e for e in entities if 'kai_chuang' in e or '1001' in e or '500' in e]
        _LOGGER.info("  [HA验证] %s: 总实体=%d, 开窗器相关=%d", label, len(entities), len(kc))
        return entities, kc

    # ---- 阶段 0: 快速验证 ----
    async def _phase_quick_verify(self):
        self._log_phase("0/9: 快速验证 (1 网关 × 001)")
        sn = f"{GATEWAY_PREFIX}{1:06d}"
        await self._publish(self._make("001", {"vesion":"1.0","model":"快速验证","userid":"test"}, sn))
        _LOGGER.info("已发送 1 条 001 绑定")
        await asyncio.sleep(3)
        entities, kc = await self._check_entities("快速验证后")
        rsp_count = len(self._rsp_messages)
        _LOGGER.info("gateway/rsp 上收到消息: %d 条 (含自己发布的)", rsp_count)
        return f"entities={len(entities)}, kc={len(kc)}, rsp_msgs={rsp_count}"

    # ---- 阶段 1: 批量添加网关 ----
    async def _phase_add_gateways(self):
        self._log_phase("1/9: 批量添加网关 (50 × 001)")
        for i in range(GATEWAY_COUNT):
            sn = f"{GATEWAY_PREFIX}{i+1:06d}"
            await self._publish(self._make("001", {"vesion":"1.0","model":f"慧尖网关{sn[-4:]}","userid":"test"}, sn))
            if i % 10 == 0: _LOGGER.info("  %d/50", i)
            await asyncio.sleep(0.01)
        _LOGGER.info("已发送 50 个 001")
        await asyncio.sleep(3)
        entities, kc = await self._check_entities("添加网关后")
        return f"sent 50, entities={len(entities)}, kc={len(kc)}"

    # ---- 阶段 2: 批量添加子设备 ----
    async def _phase_add_devices(self):
        self._log_phase("2/9: 批量添加子设备 (50×10=500)")
        for i in range(GATEWAY_COUNT):
            gw_sn = f"{GATEWAY_PREFIX}{i+1:06d}"
            devices = [{"sn": f"{DEVICE_PREFIX}{(i*DEVICES_PER_GATEWAY+d+1):07d}", "model":"window_opener", "vesion":"1.0",
                        "battery":str(random.randint(80,120)), "r_travel":str(random.choice([0,50,100]))}
                       for d in range(DEVICES_PER_GATEWAY)]
            await self._publish(self._make("002", {"status":"online","devices":devices}, gw_sn))
            if i % 10 == 0: _LOGGER.info("  %d/50", i)
            await asyncio.sleep(0.03)
        _LOGGER.info("已发送 50 个 002")
        await asyncio.sleep(8)
        entities, kc = await self._check_entities("添加设备后")
        return f"sent 50, entities={len(entities)}, kc={len(kc)}"

    # ---- 阶段 3: 并发状态更新 ----
    async def _phase_concurrent_status(self):
        self._log_phase("3/9: 并发状态更新 (500×3轮=1500)")
        for rnd in range(3):
            _LOGGER.info("--- 第 %d/3 轮 ---", rnd+1)
            tasks = []
            for i in range(GATEWAY_COUNT):
                gw_sn = f"{GATEWAY_PREFIX}{i+1:06d}"
                for d in range(DEVICES_PER_GATEWAY):
                    dev_sn = f"{DEVICE_PREFIX}{(i*DEVICES_PER_GATEWAY+d+1):07d}"
                    tasks.append(self._publish(self._make("005", {
                        "sn":dev_sn, "status":random.choice(["closed","open"]),
                        "attrs":[{"attribute":"r_travel","value":str(random.choice([0,50,100]))},
                                 {"attribute":"voltage","value":str(random.randint(80,120))}]
                    }, gw_sn)))
            await asyncio.gather(*tasks, return_exceptions=True)
            _LOGGER.info("  第 %d 轮: %d 条", rnd+1, len(tasks))
            await asyncio.sleep(3)
        entities, kc = await self._check_entities("状态更新后")
        return f"sent 1500, entities={len(entities)}, kc={len(kc)}"

    # ---- 阶段 4: 设备控制 ----
    async def _phase_control(self):
        self._log_phase("4/9: 设备控制 (500 响应)")
        cmds_before = len(self._ha_cmds)
        for i in range(GATEWAY_COUNT):
            gw_sn = f"{GATEWAY_PREFIX}{i+1:06d}"
            for d in range(DEVICES_PER_GATEWAY):
                dev_sn = f"{DEVICE_PREFIX}{(i*DEVICES_PER_GATEWAY+d+1):07d}"
                await self._publish(self._make("004", {"errcode":0,"sn":dev_sn}, gw_sn))
            if i % 10 == 0: _LOGGER.info("  %d/50", i)
            await asyncio.sleep(0.01)
        await asyncio.sleep(2)
        _LOGGER.info("HA 命令: %d 条 (新增 %d)", len(self._ha_cmds), len(self._ha_cmds)-cmds_before)
        return f"sent 500, ha_cmds={len(self._ha_cmds)-cmds_before}"

    # ---- 阶段 5: 删除子设备 ----
    async def _phase_delete_devices(self):
        self._log_phase("5/9: 删除子设备 (20 个)")
        gw_sn = f"{GATEWAY_PREFIX}{1:06d}"
        remove_sns = [f"{DEVICE_PREFIX}{(d+1):07d}" for d in range(20)]
        for sn in remove_sns:
            await self._ha_post("services/window_controller_gateway/remove_device", {"gateway_sn":gw_sn,"device_sn":sn})
            await asyncio.sleep(0.05)
        _LOGGER.info("已请求删除 20 个")
        await asyncio.sleep(3)
        entities, kc = await self._check_entities("删除后")
        remaining = [e for e in entities if any(s in e for s in remove_sns)]
        return f"deleted 20, remaining={len(remaining)}"

    # ---- 阶段 6: 迁移 ----
    async def _phase_migrate(self):
        self._log_phase("6/9: 迁移 (网关1→网关2)")
        old, new = f"{GATEWAY_PREFIX}{1:06d}", f"{GATEWAY_PREFIX}{2:06d}"
        await self._ha_post("services/window_controller_gateway/migrate_devices", {"old_gateway_sn":old,"new_gateway_sn":new,"remove_old_gateway":False})
        _LOGGER.info("迁移: %s -> %s", old, new)
        await asyncio.sleep(5)
        entities, kc = await self._check_entities("迁移后")
        old_e = [e for e in entities if old in e]; new_e = [e for e in entities if new in e]
        return f"old_gw={len(old_e)}, new_gw={len(new_e)}"

    # ---- 阶段 7: 删除网关 ----
    async def _phase_delete_gateway(self):
        self._log_phase("7/9: 删除网关 (网关3)")
        gw_sn = f"{GATEWAY_PREFIX}{3:06d}"
        await self._ha_post("services/window_controller_gateway/remove_device", {"gateway_sn":gw_sn,"device_sn":gw_sn})
        _LOGGER.info("删除网关: %s", gw_sn)
        await asyncio.sleep(3)
        entities, kc = await self._check_entities("删除网关后")
        remaining = [e for e in entities if gw_sn in e]
        return f"remaining={len(remaining)}"

    # ---- 阶段 8: 采集指标 ----
    async def _phase_metrics(self):
        self._log_phase("8/9: 采集指标")
        entities = await self._get_entity_ids()
        self._entities_after = entities
        self.report.entities_before = len(self._entities_before)
        self.report.entities_after = len(entities)
        domain_counts = {}
        for eid in entities:
            d = eid.split(".")[0]; domain_counts[d] = domain_counts.get(d,0)+1
        _LOGGER.info("HA 实体统计:")
        for d,c in sorted(domain_counts.items()): _LOGGER.info("  %s: %d", d, c)
        wc_domains = ["button","sensor","binary_sensor","cover"]
        actual = sum(domain_counts.get(d,0) for d in wc_domains)
        expected = GATEWAY_COUNT*DEVICES_PER_GATEWAY*5 + GATEWAY_COUNT*2
        self.report.ha_entities_found = actual; self.report.ha_entities_expected = expected
        rate = (actual/expected*100) if expected > 0 else 0
        self.report.device_registration_rate = f"{rate:.1f}%"
        self.report.mqtt_sent = self._mqtt_sent
        self.report.mqtt_received_on_rsp = len(self._rsp_messages)
        self.report.ha_commands = len(self._ha_cmds)
        _LOGGER.info("测试前=%d 测试后=%d 新增=%d", self.report.entities_before, self.report.entities_after, self.report.entities_after-self.report.entities_before)
        _LOGGER.info("预期=%d 实际=%d 注册率=%s", expected, actual, self.report.device_registration_rate)
        _LOGGER.info("MQTT发送=%d gateway/rsp收到=%d HA命令=%d", self._mqtt_sent, len(self._rsp_messages), len(self._ha_cmds))
        return f"entities={len(entities)}, rate={self.report.device_registration_rate}"

    async def run(self):
        self._start_time = time.time()
        _LOGGER.info(""); _LOGGER.info("="*60)
        _LOGGER.info("慧尖开窗器网关 - 优化版压力测试")
        _LOGGER.info("MQTT: %s:%s  模拟: %d网关×%d设备=%d台", MQTT_HOST, MQTT_PORT, GATEWAY_COUNT, DEVICES_PER_GATEWAY, GATEWAY_COUNT*DEVICES_PER_GATEWAY)
        _LOGGER.info("="*60)
        listener_rsp = listener_req = None
        try:
            await self._connect()
            listener_rsp = asyncio.create_task(self._listen_rsp())
            listener_req = asyncio.create_task(self._listen_req())
            await asyncio.sleep(0.5)
            self._entities_before = await self._get_entity_ids()
            _LOGGER.info("测试前 HA 实体数: %d", len(self._entities_before))
            phases = [
                ("快速验证", self._phase_quick_verify()),
                ("添加网关", self._phase_add_gateways()),
                ("添加子设备", self._phase_add_devices()),
                ("并发状态更新", self._phase_concurrent_status()),
                ("设备控制", self._phase_control()),
                ("删除子设备", self._phase_delete_devices()),
                ("迁移", self._phase_migrate()),
                ("删除网关", self._phase_delete_gateway()),
                ("采集指标", self._phase_metrics()),
            ]
            for name, coro in phases:
                await self._run_phase(name, coro)
        except Exception as e:
            _LOGGER.error("测试异常: %s", e, exc_info=True)
            self._errors += 1
        finally:
            self._stop_listener = True
            for t in [listener_rsp, listener_req]:
                if t: t.cancel()
            if self._mqtt: await self._mqtt.__aexit__(None,None,None)
            if self._session: await self._session.close()
            self._generate_report()

    def _generate_report(self):
        total_dur = (time.time()-self._start_time)*1000
        self.report.total_duration_ms = round(total_dur,1)
        self.report.total_errors = self._errors
        self.report.overall_passed = all(p.success for p in self.report.phases.values()) and self._errors == 0
        _LOGGER.info(""); _LOGGER.info("="*60)
        _LOGGER.info("📊 测试报告"); _LOGGER.info("="*60)
        _LOGGER.info("MQTT: %s:%s  网关: %d  设备: %d", MQTT_HOST, MQTT_PORT, GATEWAY_COUNT, GATEWAY_COUNT*DEVICES_PER_GATEWAY)
        _LOGGER.info("MQTT发送: %d  gateway/rsp收到: %d  HA命令: %d", self._mqtt_sent, len(self._rsp_messages), len(self._ha_cmds))
        _LOGGER.info("总耗时: %.0fms  总错误: %d", self.report.total_duration_ms, self.report.total_errors)
        _LOGGER.info("测试前实体: %d  测试后实体: %d  新增: %d", self.report.entities_before, self.report.entities_after, self.report.entities_after-self.report.entities_before)
        _LOGGER.info("设备注册率: %s", self.report.device_registration_rate)
        _LOGGER.info(""); _LOGGER.info("阶段结果:")
        for n,p in self.report.phases.items():
            _LOGGER.info("  %s %s: %.0fms err=%d %s", "OK" if p.success else "FAIL", p.name, p.duration_ms, p.errors, p.detail)
        _LOGGER.info(""); _LOGGER.info("总体: %s", "通过" if self.report.overall_passed else "失败"); _LOGGER.info("="*60)
        rp = os.path.join(os.path.dirname(__file__), f"stress_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        with open(rp,"w",encoding="utf-8") as f:
            json.dump({"config":{"mqtt":f"{MQTT_HOST}:{MQTT_PORT}","gateway_count":GATEWAY_COUNT,"devices_per_gateway":DEVICES_PER_GATEWAY},
                       "report":{"overall_passed":self.report.overall_passed,"total_duration_ms":self.report.total_duration_ms,
                                 "total_errors":self.report.total_errors,"mqtt_sent":self._mqtt_sent,
                                 "mqtt_received_on_rsp":len(self._rsp_messages),"ha_commands":len(self._ha_cmds),
                                 "device_registration_rate":self.report.device_registration_rate,
                                 "entities_before":self.report.entities_before,"entities_after":self.report.entities_after,
                                 "ha_entities_found":self.report.ha_entities_found,"ha_entities_expected":self.report.ha_entities_expected,
                                 "phases":{k:asdict(v) for k,v in self.report.phases.items()}},
                       "timestamp":datetime.now().isoformat()}, f, ensure_ascii=False, indent=2)
        _LOGGER.info("报告: %s", rp)

async def main():
    await StressTest().run()

if __name__ == "__main__":
    asyncio.run(main())