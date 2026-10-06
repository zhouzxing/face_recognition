import { useCallback, useEffect, useRef, useState } from 'react'
import './App.css'

const API_BASE = '/api'

function Card({ title, children, action }) {
  return (
    <section className="card">
      <div className="cardHead">
        <h2>{title}</h2>
        {action}
      </div>
      {children}
    </section>
  )
}

function StatusPill({ tone = 'muted', text }) {
  return <span className={`pill ${tone}`}>{text}</span>
}

export default function App() {
  const [employees, setEmployees] = useState([])
  const [records, setRecords] = useState([])
  const [name, setName] = useState('')
  const [employeeNo, setEmployeeNo] = useState('')
  const [registerMsg, setRegisterMsg] = useState({ tone: 'muted', text: '先录入员工人脸。' })
  const [checkMsg, setCheckMsg] = useState({ tone: 'muted', text: '上传照片后打卡。' })
  const [health, setHealth] = useState(null)

  const registerInputRef = useRef(null)
  const checkInputRef = useRef(null)

  const load = useCallback(async () => {
    const [e, r] = await Promise.all([
      fetch(`${API_BASE}/employees`).then((x) => x.json()),
      fetch(`${API_BASE}/attendance`).then((x) => x.json()),
    ])
    setEmployees(e)
    setRecords(r)
  }, [])

  const checkHealth = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/health`)
      const json = await res.json()
      setHealth(json.ok ? 'ok' : 'error')
    } catch {
      setHealth('error')
    }
  }, [])

  useEffect(() => {
    load()
    checkHealth()
  }, [load, checkHealth])

  const registerEmployee = async (e) => {
    e.preventDefault()
    const file = registerInputRef.current?.files?.[0]
    if (!file || !name.trim() || !employeeNo.trim()) {
      setRegisterMsg({ tone: 'bad', text: '请补齐姓名、工号和照片' })
      return
    }
    setRegisterMsg({ tone: 'muted', text: '正在提取人脸特征并保存...' })
    const fd = new FormData()
    fd.append('name', name.trim())
    fd.append('employee_no', employeeNo.trim())
    fd.append('photo', file)
    try {
      const res = await fetch(`${API_BASE}/employees`, { method: 'POST', body: fd })
      const json = await res.json().catch(() => ({}))
      if (!res.ok) {
        setRegisterMsg({ tone: 'bad', text: json.detail || '保存失败' })
        return
      }
      setName('')
      setEmployeeNo('')
      setRegisterMsg({ tone: 'good', text: `已保存员工 ${json.employee_no || employeeNo}` })
      await load()
    } catch (err) {
      setRegisterMsg({ tone: 'bad', text: '请求失败，请检查后端是否运行' })
    }
  }

  const checkIn = async (e) => {
    e.preventDefault()
    const file = checkInputRef.current?.files?.[0]
    if (!file) {
      setCheckMsg({ tone: 'bad', text: '请选择照片' })
      return
    }
    setCheckMsg({ tone: 'muted', text: '正在识别人脸...' })
    const fd = new FormData()
    fd.append('photo', file)
    try {
      const res = await fetch(`${API_BASE}/attendance`, { method: 'POST', body: fd })
      const json = await res.json().catch(() => ({}))
      if (!res.ok) {
        setCheckMsg({ tone: 'bad', text: json.detail || '打卡失败' })
        return
      }
      if (json.ok) {
        setCheckMsg({ tone: 'good', text: `识别成功：${json.employee.name} (${json.employee.employee_no})，分数 ${json.match_score.toFixed(3)}` })
      } else {
        setCheckMsg({ tone: 'bad', text: `未匹配：${json.note || 'unknown face'}，分数 ${json.match_score?.toFixed(3) ?? '0.000'}` })
      }
      await load()
    } catch {
      setCheckMsg({ tone: 'bad', text: '请求失败，请检查后端是否运行' })
    }
  }

  return (
    <div className="shell">
      <header className="topbar">
        <div>
          <h1>人脸考勤系统</h1>
          <p className="subtle">React + Vite · FastAPI · 人脸特征匹配</p>
        </div>
        <div className="healthWrap">
          <StatusPill tone={health === 'ok' ? 'good' : health === 'error' ? 'bad' : 'muted'} text={health === 'ok' ? 'API 正常' : health === 'error' ? 'API 异常' : '检查中'} />
        </div>
      </header>

      <main className="grid">
        <Card title="员工录入">
          <form onSubmit={registerEmployee} className="stack">
            <label className="field">
              姓名
              <input value={name} onChange={(e) => setName(e.target.value)} placeholder="张三" />
            </label>
            <label className="field">
              工号
              <input value={employeeNo} onChange={(e) => setEmployeeNo(e.target.value)} placeholder="E001" />
            </label>
            <label className="field">
              人脸照片
              <input ref={registerInputRef} type="file" accept="image/*" />
            </label>
            <button type="submit">保存员工</button>
            <div className="msg"><StatusPill tone={registerMsg.tone} text={registerMsg.text} /></div>
          </form>
        </Card>

        <Card title="打卡登记">
          <form onSubmit={checkIn} className="stack">
            <label className="field">
              打卡照片
              <input ref={checkInputRef} type="file" accept="image/*" />
            </label>
            <button type="submit">开始打卡</button>
            <div className="msg"><StatusPill tone={checkMsg.tone} text={checkMsg.text} /></div>
          </form>
        </Card>

        <Card title="员工列表" action={<button type="button" className="mini" onClick={load}>刷新</button>}>
          {employees.length === 0 ? <p className="empty">暂无员工</p> : (
            <table>
              <thead>
                <tr><th>工号</th><th>姓名</th></tr>
              </thead>
              <tbody>
                {employees.map((e) => (
                  <tr key={e.id}><td>{e.employee_no}</td><td>{e.name}</td></tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>

        <Card title="考勤记录" action={<button type="button" className="mini" onClick={load}>刷新</button>}>
          {records.length === 0 ? <p className="empty">暂无记录</p> : (
            <table>
              <thead>
                <tr><th>时间</th><th>工号</th><th>状态</th><th>分数</th></tr>
              </thead>
              <tbody>
                {records.slice(0, 10).map((r) => (
                  <tr key={r.id}>
                    <td>{new Date(r.timestamp * 1000).toLocaleString()}</td>
                    <td>{r.employee_no || 'unknown'}</td>
                    <td><StatusPill tone={r.status === 'success' ? 'good' : 'bad'} text={r.status === 'success' ? '成功' : '失败'} /></td>
                    <td>{r.match_score?.toFixed(3) ?? '0.000'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </main>
    </div>
  )
}
