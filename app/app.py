from __future__ import annotations
import hashlib, time
from pathlib import Path
from typing import Any, Optional
import cv2, face_recognition, numpy as np
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel, Field as PydField
from sqlmodel import Field, SQLModel, Session, create_engine, select

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'data'
UPLOAD_DIR = DATA_DIR / 'uploads'
DB_PATH = DATA_DIR / 'face_workhour.db'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
FACE_MATCH_TOLERANCE = 0.5

class Employee(SQLModel, table=True):
    __tablename__ = 'employees'
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    employee_no: str = Field(index=True, unique=True)
    department: str = ''
    phone: str = ''
    face_hash: str = ''
    face_vector: bytes = b''
    photo_path: str = ''
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

class Attendance(SQLModel, table=True):
    __tablename__ = 'attendance'
    id: Optional[int] = Field(default=None, primary_key=True)
    employee_id: int = 0
    employee_no: str = ''
    employee_name: str = ''
    face_hash: str = ''
    face_vector: bytes = b''
    photo_path: str = ''
    timestamp: float = Field(default_factory=time.time)
    status: str = 'success'
    match_score: float = 0.0
    note: str = ''

engine = create_engine(f'sqlite:///{DB_PATH}')
SQLModel.metadata.create_all(engine)

class EmployeeUpdate(BaseModel):
    name: Optional[str] = PydField(default=None, min_length=1, max_length=80)
    employee_no: Optional[str] = PydField(default=None, min_length=1, max_length=64)
    department: Optional[str] = ''
    phone: Optional[str] = ''

def get_session():
    with Session(engine) as session:
        yield session

def employee_out(e: Employee) -> dict[str, Any]:
    return {'id': e.id, 'name': e.name, 'employee_no': e.employee_no, 'department': e.department, 'phone': e.phone, 'photo_path': e.photo_path, 'created_at': e.created_at, 'updated_at': e.updated_at}

def attendance_out(r: Attendance) -> dict[str, Any]:
    return {'id': r.id, 'employee_id': r.employee_id, 'employee_no': r.employee_no, 'employee_name': r.employee_name, 'timestamp': r.timestamp, 'status': r.status, 'match_score': r.match_score, 'note': r.note, 'photo_path': r.photo_path}

def require_text(value: str, field: str, max_len: int = 80) -> str:
    clean = value.strip()
    if not clean:
        raise HTTPException(400, f'{field} required')
    if len(clean) > max_len:
        raise HTTPException(400, f'{field} too long')
    return clean

def decode_bgr(data: bytes) -> np.ndarray:
    if not data:
        raise HTTPException(400, 'photo required')
    arr = np.frombuffer(data, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(422, 'invalid image file')
    return img

def encode_upload(data: bytes, prefix: str) -> str:
    digest = hashlib.sha1(data).hexdigest()[:12]
    name = f'{prefix}_{int(time.time() * 1000)}_{digest}.jpg'
    path = UPLOAD_DIR / name
    path.write_bytes(data)
    return str(path.relative_to(BASE_DIR))

def extract_face_vector(bgr: np.ndarray) -> tuple[str, bytes]:
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    boxes = face_recognition.face_locations(rgb, model='hog')
    if not boxes:
        return '', b''
    encodings = face_recognition.face_encodings(rgb, known_face_locations=boxes, model='hog')
    if not encodings:
        return '', b''
    encoding = np.asarray(encodings[0], dtype='<f4')
    vec_bytes = encoding.tobytes()
    return hashlib.sha1(vec_bytes).hexdigest(), vec_bytes

def cosine_similarity(a: bytes, b: bytes) -> float:
    if not a or not b:
        return 0.0
    va = np.frombuffer(a, dtype=np.float32)
    vb = np.frombuffer(b, dtype=np.float32)
    if va.shape != vb.shape:
        return 0.0
    na = float(np.linalg.norm(va))
    nb = float(np.linalg.norm(vb))
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))

def best_match(vector: bytes, employees: list[Employee]) -> tuple[Optional[Employee], float]:
    best = None
    best_score = 0.0
    for emp in employees:
        if not emp.face_vector:
            continue
        score = cosine_similarity(vector, emp.face_vector)
        if score > best_score:
            best, best_score = emp, score
    return best, best_score

app = FastAPI(title='Face Recognition Attendance API')

# 跨域问题
# app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=True, allow_methods=['*'], allow_headers=['*'])   


@app.get('/api/health')
def health():
    return {'ok': True, 'service': 'face_recognition_attendance', 'db': str(DB_PATH)}

@app.get('/api/employees')
def list_employees(session=Depends(get_session)):
    return [employee_out(e) for e in session.exec(select(Employee).order_by(Employee.created_at.desc())).all()]

@app.get('/api/employees/{employee_id}')
def get_employee(employee_id: int, session=Depends(get_session)):
    emp = session.get(Employee, employee_id)
    if not emp:
        raise HTTPException(404, 'employee not found')
    return employee_out(emp)

@app.post('/api/employees', status_code=201)
async def create_employee(name: str = Form(...), employee_no: str = Form(...), department: str = Form(''), phone: str = Form(''), photo: UploadFile = File(...), session=Depends(get_session)):
    name = require_text(name, 'name')
    employee_no = require_text(employee_no, 'employee_no', 64)
    department = (department or '').strip()
    phone = (phone or '').strip()
    existing = session.exec(select(Employee).where(Employee.employee_no == employee_no)).first()
    if existing:
        raise HTTPException(409, 'employee_no already exists')
    data = await photo.read()
    bgr = decode_bgr(data)
    face_hash, vector = extract_face_vector(bgr)
    if not vector:
        raise HTTPException(422, 'no face detected')
    emp = Employee(name=name, employee_no=employee_no, department=department, phone=phone, face_hash=face_hash, face_vector=vector, photo_path=encode_upload(data, 'emp'))
    session.add(emp); session.commit(); session.refresh(emp)
    return employee_out(emp)

@app.patch('/api/employees/{employee_id}')
async def update_employee(employee_id: int, request: Request, session=Depends(get_session)):
    emp = session.get(Employee, employee_id)
    if not emp:
        raise HTTPException(404, 'employee not found')
    content_type = request.headers.get('content-type', '')
    if content_type.startswith('multipart/form-data'):
        form = await request.form()
        data_map = {k: (v.decode() if hasattr(v, 'decode') else str(v)) for k, v in form.items() if not hasattr(v, 'read')}
        payload = EmployeeUpdate(**{k: data_map.get(k, None) for k in EmployeeUpdate.model_fields.keys() if data_map.get(k) is not None})
        upload = form.get('photo')
        photo = UploadFile(file=upload) if upload is not None else None
    else:
        raw = await request.body()
        payload = EmployeeUpdate.model_validate(raw or {})
        photo = None
    if payload.employee_no and payload.employee_no.strip() != emp.employee_no:
        new_no = require_text(payload.employee_no, 'employee_no', 64)
        dup = session.exec(select(Employee).where(Employee.employee_no == new_no, Employee.id != employee_id)).first()
        if dup:
            raise HTTPException(409, 'employee_no already exists')
        emp.employee_no = new_no
    if payload.name:
        emp.name = require_text(payload.name, 'name')
    if payload.department is not None:
        emp.department = payload.department.strip()
    if payload.phone is not None:
        emp.phone = payload.phone.strip()
    if photo is not None:
        data = await photo.read()
        bgr = decode_bgr(data)
        face_hash, vector = extract_face_vector(bgr)
        if not vector:
            raise HTTPException(422, 'no face detected')
        emp.face_hash = face_hash
        emp.face_vector = vector
        emp.photo_path = encode_upload(data, 'emp')
    emp.updated_at = time.time(); session.add(emp); session.commit(); session.refresh(emp)
    return employee_out(emp)

@app.delete('/api/employees/{employee_id}')
def delete_employee(employee_id: int, session=Depends(get_session)):
    emp = session.get(Employee, employee_id)
    if not emp:
        raise HTTPException(404, 'employee not found')
    if emp.photo_path:
        photo = BASE_DIR / emp.photo_path
        if photo.exists():
            photo.unlink()
    records = session.exec(select(Attendance).where(Attendance.employee_id == employee_id)).all()
    for r in records:
        if r.photo_path:
            p = BASE_DIR / r.photo_path
            if p.exists():
                p.unlink()
        session.delete(r)
    session.delete(emp); session.commit()
    return {'ok': True}

@app.post('/api/attendance', status_code=201)
async def attendance_check(photo: UploadFile = File(...), session=Depends(get_session)):
    data = await photo.read()
    bgr = decode_bgr(data)
    face_hash, vector = extract_face_vector(bgr)
    rel = encode_upload(data, 'check')
    employees = list(session.exec(select(Employee)).all())
    best, score = best_match(vector, employees) if vector else (None, 0.0)
    accepted = bool(vector and best is not None and score >= (1.0 - FACE_MATCH_TOLERANCE))
    rec = Attendance(employee_id=best.id if accepted and best is not None else 0, employee_no=best.employee_no if accepted and best is not None else '', employee_name=best.name if accepted and best is not None else '', face_hash=face_hash, face_vector=vector, photo_path=rel, status='success' if accepted else 'failure', match_score=score, note='matched' if accepted else ('no face detected' if not vector else 'no match'))
    session.add(rec); session.commit(); session.refresh(rec)
    return {'ok': accepted, 'attendance': attendance_out(rec), 'employee': employee_out(best) if accepted and best is not None else None, 'match_score': score, 'note': rec.note}

@app.get('/api/attendance')
def list_attendance(session=Depends(get_session)):
    return [attendance_out(r) for r in session.exec(select(Attendance).order_by(Attendance.timestamp.desc())).all()]

@app.get('/api/attendance/{record_id}')
def get_attendance(record_id: int, session=Depends(get_session)):
    rec = session.get(Attendance, record_id)
    if not rec:
        raise HTTPException(404, 'attendance record not found')
    return attendance_out(rec)

@app.delete('/api/attendance/{record_id}')
def delete_attendance(record_id: int, session=Depends(get_session)):
    rec = session.get(Attendance, record_id)
    if not rec:
        raise HTTPException(404, 'attendance record not found')
    if rec.photo_path:
        p = BASE_DIR / rec.photo_path
        if p.exists():
            p.unlink()
    session.delete(rec); session.commit()
    return {'ok': True}
