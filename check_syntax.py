import ast
import os

files_to_check = [
    'custom_components/window_controller_gateway/device_manager.py',
    'custom_components/window_controller_gateway/mqtt_handler.py',
    'custom_components/window_controller_gateway/sensor.py'
]

for file_path in files_to_check:
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            ast.parse(content)
            print(f"{file_path}: OK")
        except SyntaxError as e:
            print(f"{file_path}: SyntaxError at line {e.lineno}, column {e.offset}: {e.msg}")
        except Exception as e:
            print(f"{file_path}: Error: {str(e)}")
    else:
        print(f"{file_path}: File not found")
