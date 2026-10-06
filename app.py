from __future__ import annotations

import base64
import hashlib
import io
import time
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from PIL import Image
from sqlmodel import Field, SQLModel, Session, create_engine, select

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class Employee(SQLModel, table=True):
    __tablename__ = "employees"
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    employee_no: str = Field(index=True, unique=True)
    photo_hash: str
    photo_path: str = ""
    created_at: float = Field(default_factory=time.time)


class Attendance(SQLModel, table=True):
    __tablename__ = "attendance"
    id: Optional[int] = Field(default=None, primary_key=True)
    employee_id: int = 0
    employee_no: str = ""
    photo_hash: str = ""
    photo_path: str = ""
    timestamp: float = Field(default_factory=time.time)
    status: str = "success"
    note: str = ""


engine = create_engine(f"sqlite:///{DATA_DIR / 'face_workhour.db'}")
SQLModel.metadata.create_all(engine)


def get_session():
    with Session(engine) as session:
        yield session


def image_hash(data: bytes) -> str:
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img = img.resize((128, 128))
    # raw = "".join(f"{p:02x}" for p in img.tobytes())
    # return hashlib.sha1(raw.encode()).hexdigest()
    return hashlib.sha1(img.tobytes()).hexdigest()


def save_upload(data: bytes, prefix: str) -> str:
    digest = hashlib.sha1(data).hexdigest()[:10]
    name = f"{prefix}_{int(time.time()*1000)}_{digest}.jpg"
    path = UPLOAD_DIR / name
    path.write_bytes(data)
    return str(path.relative_to(BASE_DIR))


app = FastAPI(title="Face Workhour App")


@app.get("/api/health")
def health():
    return {"ok": True}


@app.post("/api/employees")
async def create_employee(name: str = Form(...), employee_no: str = Form(...), photo: UploadFile = File(...), session=Depends(get_session)):
    data = await photo.read()
    if not data:
        raise HTTPException(400, "photo required")
    if not name.strip() or not employee_no.strip():
        raise HTTPException(400, "name and employee_no required")
    if session.exec(select(Employee).where(Employee.employee_no == employee_no)).first():
        raise HTTPException(409, "employee_no already exists")
    h = image_hash(data)
    rel = save_upload(data, "emp")
    emp = Employee(name=name.strip(), employee_no=employee_no.strip(), photo_hash=h, photo_path=rel)
    session.add(emp)
    session.commit()
    session.refresh(emp)
    return {"id": emp.id, "name": emp.name, "employee_no": emp.employee_no}


@app.post("/api/attendance")
async def attendance_check(photo: UploadFile = File(...), session=Depends(get_session)):
    data = await photo.read()
    if not data:
        raise HTTPException(400, "photo required")
    h = image_hash(data)
    rel = save_upload(data, "check")
    emp = session.exec(select(Employee).where(Employee.photo_hash == h)).first()
    if emp:
        rec = Attendance(employee_id=emp.id, employee_no=emp.employee_no, photo_hash=h, photo_path=rel, status="success")
    else:
        rec = Attendance(photo_hash=h, photo_path=rel, status="failure", note="no exact match")
    session.add(rec)
    session.commit()
    return {
        "ok": bool(emp),
        "employee": {"id": emp.id, "name": emp.name, "employee_no": emp.employee_no} if emp else None,
        "note": rec.note,
    }


@app.get("/api/employees")
def list_employees(session=Depends(get_session)):
    return [{"id": e.id, "name": e.name, "employee_no": e.employee_no} for e in session.exec(select(Employee)).all()]


@app.get("/api/attendance")
def list_attendance(session=Depends(get_session)):
    rows = session.exec(select(Attendance).order_by(Attendance.timestamp.desc())).all()
    return [{"id": r.id, "employee_no": r.employee_no, "timestamp": r.timestamp, "status": r.status, "note": r.note} for r in rows]


@app.get("/", response_class=HTMLResponse)
def index():
    return """
<!doctype html><html><head><meta charset='utf-8'><title>Face Workhour</title>
<style>body{font-family:Arial;margin:0;background:#f8fafc;color:#111827}header{background:#0f172a;color:#fff;padding:18px 22px}main{max-width:1000px;margin:24px auto;padding:0 16px;display:grid;gap:16px;grid-template-columns:1fr 1fr}.card{background:#fff;border:1px solid #e5e7eb;border-radius:14px;padding:16px}input,button{width:100%;padding:10px;border-radius:10px;border:1px solid #cbd5e1;box-sizing:border-box}button{border:0;background:#2563eb;color:#fff;cursor:pointer;margin-top:8px}.muted{color:#64748b;font-size:13px}.note{background:#f1f5f9;border:1px solid #e2e8f0;border-radius:10px;padding:10px;min-height:40px}.pill{padding:3px 8px;border-radius:999px;font-size:12px}.ok{background:#dcfce7;color:#166534}.bad{background:#fee2e2;color:#991b1b}</style></head>
<body><header><strong>人脸考勤</strong></header><main>
<section class='card'><h2>员工录入</h2><input id='name' placeholder='姓名'><input id='no' placeholder='工号'><input type='file' id='photo'><button onclick='register()'>保存</button><div class='note' id='msg1'>先录入员工。</div></section>
<section class='card'><h2>打卡</h2><input type='file' id='check'><button onclick='checkin()'>打卡</button><div class='note' id='msg2'>选择照片后打卡。</div></section>
<section class='card'><h2>员工</h2><div id='emps'></div></section><section class='card'><h2>记录</h2><div id='recs'></div></section>
</main><script>
function fmt(t){return new Date(t*1000).toLocaleString()}
async function post(url, fd){return (await fetch(url,{method:'POST',body:fd})).json()}
function fileForm(id,f){let i=document.getElementById(id);if(!i.files[0])return null;let fd=new FormData();fd.append(f,i.files[0]);return fd}
async function register(){
    let n=document.getElementById('name').value.trim(),
        e=document.getElementById('no').value.trim(),
        f=fileForm('photo','photo');
    if(!n||!e||!f){
        document.getElementById('msg1').textContent='请补齐信息';
        return
    }
    f.append('name',n);
    f.append('employee_no',e);
    document.getElementById('msg1').textContent='处理中...';
    let r=await post('/api/employees',f);
    document.getElementById('msg1').innerHTML='<span class=pill ok>成功</span>'+r.employee_no;
    load()
}
async function checkin(){let f=fileForm('check','photo');if(!f){document.getElementById('msg2').textContent='请选择照片';return}document.getElementById('msg2').textContent='识别中...';let r=await post('/api/attendance',f);document.getElementById('msg2').innerHTML=r.ok?'<span class=pill ok>成功</span>'+r.employee.employee_no:'<span class=pill bad>失败</span>'+(r.note||'未匹配');load()}
async function load(){let e=await (await fetch('/api/employees')).json();let r=await (await fetch('/api/attendance')).json();document.getElementById('emps').innerHTML=e.length?e.map(x=>`<div>${x.employee_no} - ${x.name}</div>`).join(''):'<div class=muted>暂无</div>';document.getElementById('recs').innerHTML=r.length?r.slice(0,10).map(x=>`<div>${fmt(x.timestamp)} · ${x.employee_no||'unknown'} · ${x.status}</div>`).join(''):'<div class=muted>暂无</div>'}
load();</script></body></html>"""



'''bugfix
    - async function register(){let n=document.getElementById('name').value.trim(),e=document.getElementById('no').value.trim(),f=fileForm('photo','photo');if(!n||!e||!f){document.getElementById('msg1').textContent='请补齐信息';return}let fd=new FormData();fd.append('name',n);fd.append('employee_no',e);fd.append('photo',f.get('photo')[0]);document.getElementById('msg1').textContent='处理中...';let r=await post('/api/employees',fd);document.getElementById('msg1').innerHTML='<span class=pill ok>成功</span>'+r.employee_no;load()}
    - 
'''