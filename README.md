# Face Workhour App

## 原型验证
基于 FastAPI + SQLite + Pillow 的人脸考勤 Web 应用（最小可用版）。
功能

    员工录入（姓名、工号、照片）
    打卡登记（上传照片）
    识别结果记录到 SQLite
    简单的 Web 界面：录入 / 打卡 / 查看列表

运行

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --port 8000

浏览器打开：

    http://127.0.0.1:8000/
    http://127.0.0.1:8000/api/health

说明

    当前识别逻辑是“照片指纹精确匹配”的最小闭环，用于先跑通业务流。
    后续可替换为真正的深度学习人脸特征匹配。


## v2.0 升级日志
- 前后端分离
- 后端图像识别：
    - opencv-python: 图片解码， 
        - cv2.imdecode(arr, cv2.IMREAD_COLOR)
        - cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    face_recognition: hog模型做人脸识别
        - face_recognition.face_locations(rgb, model='hog') # 人脸识别
        - face_recognition.face_encodings(rgb, known_face_locations=boxes, model='hog') # 人脸数据编码
        - cosine_similarity(vector, emp.face_vector) # 人脸张量匹配 - 余弦积 得分 > 0.5 可手动调整！ <- 伪造打卡图片/
        


## v3.0 

- 前端
    - 页面更商业化，布局扁平化：
    - 增加批量导入功能
- 后端：facenet_pytorch / torch / torchvision
    - 把后端从 face_recognition 再改成 当前环境里最稳的可运行深度学习方案，然后再做一次完整冒烟验证