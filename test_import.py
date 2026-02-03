"""测试导入问题是否已解决"""
import sys
import os

# 添加集成目录到Python路径
integration_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "custom_components", "window_controller_gateway"))
sys.path.insert(0, os.path.dirname(integration_path))

def test_import():
    """测试导入集成模块"""
    print("开始测试导入...")
    
    try:
        # 尝试导入集成的__init__.py模块
        from custom_components.window_controller_gateway import async_setup
        print("✅ 成功导入 async_setup 函数")
        
        # 尝试导入config_flow模块
        from custom_components.window_controller_gateway.config_flow import ConfigFlow
        print("✅ 成功导入 ConfigFlow 类")
        
        print("\n🎉 所有导入测试通过！导入问题已解决。")
        return True
        
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        if "async_register_static_path" in str(e):
            print("⚠️  仍然存在 async_register_static_path 导入问题")
        return False
    except Exception as e:
        print(f"❌ 其他错误: {e}")
        return False

if __name__ == "__main__":
    test_import()
