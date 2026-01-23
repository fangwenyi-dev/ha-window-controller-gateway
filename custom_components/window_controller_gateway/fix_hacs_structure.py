# HACS仓库结构修复指南
# 错误：Repository structure for v1.0.0 is not compliant

import os
import json

# 检查当前目录结构
def check_structure():
    print("=== 当前目录结构 ===")
    for root, dirs, files in os.walk("."):
        level = root.replace(".", "").count(os.sep)
        indent = " " * 2 * level
        print(f"{indent}{os.path.basename(root)}/")
        subindent = " " * 2 * (level + 1)
        for file in files[:10]:  # 只显示前10个文件
            print(f"{subindent}{file}")
        if len(files) > 10:
            print(f"{subindent}... 还有 {len(files) - 10} 个文件")

# HACS合规结构要求
def hacs_requirements():
    print("\n=== HACS仓库结构要求 ===")
    print("1. 根目录必须包含：")
    print("   - .hacs.json (HACS配置文件)")
    print("   - README.md (说明文档)")
    print("   - custom_components/ (集成目录)")
    print("2. custom_components/目录下必须有：")
    print("   - window_controller_gateway/ (与domain同名)")
    print("3. window_controller_gateway/目录下必须包含：")
    print("   - __init__.py")
    print("   - manifest.json")
    print("   - 其他集成文件")
    print("4. 发布标签必须符合语义化版本：v1.0.0")

# 修复建议
def fix_suggestions():
    print("\n=== 修复建议 ===")
    print("1. 检查根目录结构：")
    print("   - 确保custom_components/目录在根目录")
    print("   - 确保.hacs.json在根目录")
    print("   - 确保README.md在根目录")
    
    print("2. 检查集成目录名：")
    print("   - custom_components/下的目录名必须是window_controller_gateway")
    
    print("3. 检查发布标签：")
    print("   - 确保tag v1.0.0指向包含正确结构的commit")
    print("   - 重新创建release，确保target branch正确")
    
    print("4. 检查.hacs.json内容：")
    print("   - name：集成名称")
    print("   - render_readme：true")
    print("   - domains：集成支持的domain列表")
    print("   - homeassistant：最低支持的HA版本")

# 示例.hacs.json内容
def example_hacs_json():
    print("\n=== 示例.hacs.json内容 ===")
    example = {
        "name": "慧尖开窗器网关",
        "render_readme": True,
        "domains": ["cover", "binary_sensor", "button"],
        "homeassistant": "2024.11.0"
    }
    print(json.dumps(example, indent=2, ensure_ascii=False))

# 执行检查
if __name__ == "__main__":
    check_structure()
    hacs_requirements()
    fix_suggestions()
    example_hacs_json()
