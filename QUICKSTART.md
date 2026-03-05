# 🎯 DataTaxonomy — Quick Start Guide

## 快速开始（3 分钟）

### 1️⃣ 环境设置

```bash
# 安装依赖
pip install -r requirements.txt

# 创建 .env 文件
cp .env.example .env
# 编辑 .env，添加你的 OPENROUTER_API_KEY
```

### 2️⃣ 编辑配置

打开网页配置器：

```bash
streamlit run config_ui.py --server.port 8502
```

访问 http://localhost:8502，在网页中修改：
- `project.name` — 项目名称
- `paths.input_dir` — 文件夹路径
- `processing.sample_n` — 处理的文件数量

### 3️⃣ 运行程序

在配置网页中点击 `▶️ START PROCESSING` 即可开始处理。

处理完成后：
- 可在同页下载 CSV
- 按提示启动 Dashboard 查看结果

> 仅保留网页操作流（推荐）。
> 其他启动方式（CLI / GUI / 脚本）统一放在：[RUN_METHODS.md](RUN_METHODS.md)

---

## 📁 文件说明

| 文件 | 用途 |
|------|------|
| `config_ui.py` | Web 配置与运行入口（推荐） |
| `main.py` | 命令行入口（进阶） |
| `app.py` | GUI 桌面应用（进阶） |
| `dashboard.py` | Streamlit 仪表板 |
| `config.yaml` | 配置文件（无需改代码） |
| `config_loader.py` | 配置加载器 |
| `setup.py` | 包安装配置 |
| `startup.sh` | Bash 启动脚本 |
| `core/` | 核心处理逻辑 |

---

## 🚀 常见用法

### 用例 1：快速测试（20 个文件）

在配置网页中：
- `Processing` → `Files to Process` 设为 `20`
- 点击 `💾 Save Processing Settings`
- 点击 `▶️ START PROCESSING`

### 用例 2：完整处理（所有文件）

在配置网页中：
- `Processing` → 勾选 `Process ALL files`
- 点击 `💾 Save Processing Settings`
- 点击 `▶️ START PROCESSING`

### 用例 3：处理多个项目

推荐做法：
- 每个项目维护一个独立目录 + 独立 `config.yaml`
- 分别打开网页配置器并执行处理
- 避免在同一目录反复覆盖配置

### 用例 4：使用不同的 LLM

在配置网页中：
- `Processing` → `LLM Model` 选择目标模型
- 点击 `💾 Save Processing Settings`
- 点击 `▶️ START PROCESSING`

---

## 🔧 配置说明

### config.yaml 关键字段

```yaml
project:
  name: "Project Name"           # 项目名称
  location: "City, Country"      # 位置
  year_range: [2020, 2026]       # 年份范围
  lead_firm: "Firm Name"         # 主设计公司
  consultants: [...]             # 顾问列表
  authorities: [...]             # 政府部门

paths:
  input_dir: "~/Desktop/MyProject"  # 输入文件夹
  output_csv: "results.csv"         # 输出文件名

processing:
  sample_n: 20          # 文件数量（null = 全部）
  model: "model-name"   # LLM 模型

dashboard:
  port: 8501            # Streamlit 端口
  auto_launch: true     # 自动打开浏览器
```

---

## 📊 Dashboard 功能

启动后，访问 http://localhost:8501

- **Overview** — 总体统计和优先级分布
- **By Domain** — 按领域分类
- **By Priority** — 需要审查的文件
- **Data** — 数据资产列表

---

## ⚡ 快捷命令

```bash
# 启动网页配置器（推荐入口）
streamlit run config_ui.py --server.port 8502

# 启动 Dashboard（查看结果）
streamlit run dashboard.py --server.port 8501

# 安装开发依赖
pip install -e ".[dev]"
```

更多运行方式见：[RUN_METHODS.md](RUN_METHODS.md)

---

## 🐛 故障排查

**"config.yaml not found"**
- 确保在项目根目录运行

**"OPENROUTER_API_KEY not found"**
- 检查 .env 文件是否存在和正确配置

**"Input directory not found"**
- 检查 config.yaml 中 paths.input_dir 路径

**Dashboard 不打开**
- 检查 8501 端口是否被占用
- 或手动访问 http://localhost:8501

---

## 📝 工作流

```
1. 打开 config_ui 网页
   ↓
2. 保存配置并点击 START PROCESSING
  ├─ 处理文件 → 生成 CSV
  └─ 页面中可下载结果
   ↓
3. 启动 Dashboard 查看结果
   ├─ 过滤和分析
   ├─ 导出数据
   └─ 生成报告
```

---

## 🎯 典型流程

```bash
# 步骤 1：打开网页配置器
streamlit run config_ui.py --server.port 8502

# 步骤 2：在网页中保存配置并开始处理
# （点击 ▶️ START PROCESSING）

# 步骤 3：查看结果
streamlit run dashboard.py --server.port 8501

# 步骤 4：导出数据
# 在 Dashboard 中下载 CSV
```

---

## 💡 提示

- 使用 `sample_n: 20` 快速测试
- 使用 `sample_n: null` 处理全部文件
- Config.yaml 支持绝对路径和 ~ 家目录符号
- 每次修改 config.yaml 后重新运行
- Dashboard 支持热刷新（F5）

---

## 📞 需要帮助？

查看详细文档：
- [CONFIG.md](CONFIG.md) — 配置详解
- [README.md](README.md) — 项目说明
- [core/](core/) — 核心模块文档

