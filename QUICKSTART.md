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

打开 `config.yaml`，修改：
- `project.name` — 项目名称
- `paths.input_dir` — 文件夹路径
- `processing.sample_n` — 处理的文件数量

### 3️⃣ 运行程序

**选项 A：命令行（推荐）**
```bash
python main.py
```

**选项 B：图形界面**
```bash
python app.py
```

**选项 C：Bash 脚本**
```bash
chmod +x startup.sh
./startup.sh
```

**选项 D：只处理数据**
```bash
python main.py --no-dashboard
```

**选项 E：只启动 Dashboard**
```bash
streamlit run dashboard.py
```

---

## 📁 文件说明

| 文件 | 用途 |
|------|------|
| `main.py` | 命令行入口（推荐） |
| `app.py` | GUI 桌面应用（可选） |
| `dashboard.py` | Streamlit 仪表板 |
| `config.yaml` | 配置文件（无需改代码） |
| `config_loader.py` | 配置加载器 |
| `setup.py` | 包安装配置 |
| `startup.sh` | Bash 启动脚本 |
| `core/` | 核心处理逻辑 |

---

## 🚀 常见用法

### 用例 1：快速测试（20 个文件）

编辑 `config.yaml`：
```yaml
processing:
  sample_n: 20
```

运行：
```bash
python main.py
```

### 用例 2：完整处理（所有文件）

编辑 `config.yaml`：
```yaml
processing:
  sample_n: null
```

运行：
```bash
python main.py
```

### 用例 3：处理多个项目

创建多个配置文件：
```bash
cp config.yaml project1.yaml
cp config.yaml project2.yaml
```

编辑各自的配置，然后运行：
```bash
python main.py --config project1.yaml
python main.py --config project2.yaml
```

### 用例 4：使用不同的 LLM

```bash
# 使用环境变量
MODEL=anthropic/claude-opus python main.py

# 或编辑 config.yaml
processing:
  model: "anthropic/claude-opus"
```

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
# 查看帮助
python main.py --help

# 使用自定义配置
python main.py --config myconfig.yaml

# 跳过 Dashboard
python main.py --no-dashboard

# 只启动 Dashboard
streamlit run dashboard.py

# GUI 应用
python app.py

# 安装开发依赖
pip install -e ".[dev]"
```

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
1. 编辑 config.yaml
   ↓
2. python main.py
   ├─ 处理文件 → 生成 CSV
   └─ 启动 Dashboard
   ↓
3. 在 Dashboard 中查看结果
   ├─ 过滤和分析
   ├─ 导出数据
   └─ 生成报告
```

---

## 🎯 典型流程

```bash
# 步骤 1：配置项目
nano config.yaml

# 步骤 2：运行处理
python main.py

# 步骤 3：查看结果
# （自动打开 http://localhost:8501）

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

