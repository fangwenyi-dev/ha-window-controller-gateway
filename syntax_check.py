# 简单的语法检查脚本

files = [
    'custom_components/window_controller_gateway/device_manager.py',
    'custom_components/window_controller_gateway/mqtt_handler.py',
    'custom_components/window_controller_gateway/sensor.py'
]

for file in files:
    try:
        with open(file, 'r') as f:
            code = f.read()
        compile(code, file, 'exec')
        print(f"{file}: 语法正确")
    except SyntaxError as e:
        print(f"{file}: 语法错误 - 行 {e.lineno}, 列 {e.offset}: {e.msg}")
    except Exception as e:
        print(f"{file}: 错误 - {e}")
