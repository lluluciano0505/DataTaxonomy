#!/usr/bin/env python3
"""
launcher.py — 一键启动应用
双击运行或在终端执行都可以

最简单的启动方式！
"""

import subprocess
import sys
import os
from pathlib import Path


def main():
    """启动应用的最简单方式"""
    
    # 检查环境
    if not Path("config.yaml").exists():
        print("❌ 错误：找不到 config.yaml")
        print("请在项目根目录运行此脚本")
        input("按回车键退出...")
        sys.exit(1)
    
    if not Path(".env").exists():
        print("⚠️  警告：.env 文件不存在")
        print("正在创建...")
        try:
            subprocess.run(["cp", ".env.example", ".env"], check=True)
            print("✅ .env 已创建")
            print("📝 请编辑 .env，添加你的 OPENROUTER_API_KEY")
            input("按回车键继续...")
        except Exception as e:
            print(f"❌ 错误：{e}")
            input("按回车键退出...")
            sys.exit(1)
    
    print("\n" + "="*60)
    print("🎯 DataTaxonomy — 本地应用启动器")
    print("="*60)
    print("\n选择启动模式：\n")
    print("1️⃣  完整流程 (处理数据 + 启动 Dashboard)     ← 推荐")
    print("2️⃣  仅处理数据 (生成 CSV，不启动 Dashboard)")
    print("3️⃣  仅启动 Dashboard (查看已有的结果)")
    print("4️⃣  GUI 界面应用 (图形界面模式)")
    print("0️⃣  退出")
    print()
    
    while True:
        choice = input("请选择 (0-4): ").strip()
        
        if choice == "1":
            print("\n🚀 启动完整流程...\n")
            subprocess.run([sys.executable, "main.py"])
            break
        elif choice == "2":
            print("\n📊 处理数据...\n")
            subprocess.run([sys.executable, "main.py", "--no-dashboard"])
            break
        elif choice == "3":
            print("\n📈 启动 Dashboard...\n")
            subprocess.run(["streamlit", "run", "dashboard.py"])
            break
        elif choice == "4":
            print("\n🖥️  启动 GUI 应用...\n")
            subprocess.run([sys.executable, "app.py"])
            break
        elif choice == "0":
            print("👋 再见！")
            sys.exit(0)
        else:
            print("❌ 无效选择，请重试")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 已取消")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 错误：{e}")
        input("按回车键退出...")
        sys.exit(1)
