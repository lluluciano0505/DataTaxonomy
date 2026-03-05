# 🧰 DataTaxonomy — 其他运行方式（非网页主流程）

> 本文件收纳非 Web 主流程的启动方式。
> 推荐日常使用：`config_ui.py` 网页流程。

---

## 1) 命令行方式（CLI）

### 标准运行
```bash
python main.py
```

### 仅处理，不自动启动 Dashboard
```bash
python main.py --no-dashboard
```

### 并行处理（更快）
```bash
python main.py --parallel 8
```

### 指定配置文件
```bash
python main.py --config myconfig.yaml
```

### 查看帮助
```bash
python main.py --help
```

---

## 2) 仅启动 Dashboard

```bash
streamlit run dashboard.py --server.port 8501
```

浏览器访问：http://localhost:8501

---

## 3) 桌面 GUI（Tk）

```bash
python app.py
```

---

## 4) 启动脚本

### macOS / Linux
```bash
chmod +x startup.sh
./startup.sh
```

### Windows
```bat
run.bat
```

---

## 5) Conda 环境示例

```bash
conda run -p /opt/anaconda3 python main.py --no-dashboard
```

---

## 建议

- 只想简化操作：使用网页流程（`streamlit run config_ui.py`）
- 需要自动化 / 批处理 / CI：使用 CLI（`python main.py ...`）
