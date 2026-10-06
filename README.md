# Face Workhour App

基于 FastAPI + SQLite + Pillow 的人脸考勤 Web 应用（最小可用版）。

## 功能
- 员工录入（姓名、工号、照片）
- 打卡登记（上传照片）
- 识别结果记录到 SQLite
- 简单的 Web 界面：录入 / 打卡 / 查看列表

## 运行
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

浏览器打开：
- http://127.0.0.1:8000/
- http://127.0.0.1:8000/api/health

## 说明
- 当前识别逻辑是“照片指纹精确匹配”的最小闭环，用于先跑通业务流。
- 后续可替换为真正的深度学习人脸特征匹配。
