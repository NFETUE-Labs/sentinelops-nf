import { useState, useEffect, useCallback } from 'react'

const API = '/api'

function useApi(token) {
  const get = useCallback(async (path) => {
    const res = await fetch(`${API}${path}`, {
      headers: { Authorization: `Bearer ${token}` }
    })
    if (!res.ok) throw new Error(res.status)
    return res.json()
  }, [token])
  return { get }
}

function Login({ onLogin }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async () => {
    setLoading(true)
    setError('')
    try {
      const body = new URLSearchParams({ username: email, password })
      const res = await fetch(`${API}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body
      })
      if (!res.ok) { setError('Invalid credentials'); setLoading(false); return }
      const data = await res.json()
      onLogin(data.access_token)
    } catch {
      setError('Connection error')
      setLoading(false)
    }
  }

  return (
    <div style={{
      minHeight: '100vh', display: 'flex', alignItems: 'center',
      justifyContent: 'center', background: 'var(--bg)'
    }}>
      <div className="fade-in" style={{
        width: 380, padding: '40px',
        border: '1px solid var(--border)',
        background: 'var(--bg-card)'
      }}>
        <div style={{ marginBottom: 32 }}>
          <div style={{
            fontFamily: 'var(--font-display)', fontSize: 22,
            fontWeight: 800, color: 'var(--amber)', letterSpacing: '-0.5px'
          }}>SENTINELOPS</div>
          <div style={{ color: 'var(--text-dim)', marginTop: 4, fontSize: 12 }}>
            observability platform
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <input
            type="email"
            placeholder="email"
            value={email}
            onChange={e => setEmail(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && submit()}
            style={{
              background: 'var(--bg)', border: '1px solid var(--border)',
              color: 'var(--text)', padding: '10px 14px',
              fontFamily: 'var(--font-mono)', fontSize: 13, outline: 'none',
              width: '100%'
            }}
          />
          <input
            type="password"
            placeholder="password"
            value={password}
            onChange={e => setPassword(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && submit()}
            style={{
              background: 'var(--bg)', border: '1px solid var(--border)',
              color: 'var(--text)', padding: '10px 14px',
              fontFamily: 'var(--font-mono)', fontSize: 13, outline: 'none',
              width: '100%'
            }}
          />
          {error && <div style={{ color: 'var(--red)', fontSize: 12 }}>{error}</div>}
          <button
            onClick={submit}
            disabled={loading}
            style={{
              background: 'var(--amber)', color: '#000',
              border: 'none', padding: '11px',
              fontFamily: 'var(--font-mono)', fontSize: 13,
              fontWeight: 700, cursor: 'pointer',
              opacity: loading ? 0.6 : 1
            }}
          >
            {loading ? 'connecting...' : 'login →'}
          </button>
        </div>
      </div>
    </div>
  )
}

function StatCard({ label, value, accent }) {
  return (
    <div style={{
      background: 'var(--bg-card)', border: '1px solid var(--border)',
      padding: '24px', flex: 1
    }}>
      <div style={{ color: 'var(--text-dim)', fontSize: 11, marginBottom: 8, textTransform: 'uppercase', letterSpacing: 1 }}>
        {label}
      </div>
      <div style={{
        fontFamily: 'var(--font-display)', fontSize: 32,
        fontWeight: 800, color: accent || 'var(--text)'
      }}>
        {value ?? '—'}
      </div>
    </div>
  )
}

function SeverityBadge({ severity }) {
  const color = severity === 'critical' ? 'var(--red)' : 'var(--amber)'
  return (
    <span style={{
      color, border: `1px solid ${color}`,
      padding: '2px 8px', fontSize: 11, textTransform: 'uppercase', letterSpacing: 1
    }}>
      {severity}
    </span>
  )
}

function InfraBar({ label, value, color }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
        <span style={{ color: 'var(--text-dim)', fontSize: 11, textTransform: 'uppercase', letterSpacing: 1 }}>{label}</span>
        <span style={{ color: value > 90 ? 'var(--red)' : value > 70 ? 'var(--amber)' : 'var(--green)', fontWeight: 700, fontSize: 13 }}>{value}%</span>
      </div>
      <div style={{ background: 'var(--border)', height: 4, width: '100%' }}>
        <div style={{
          height: 4,
          width: `${value}%`,
          background: value > 90 ? 'var(--red)' : value > 70 ? 'var(--amber)' : 'var(--green)',
          transition: 'width 0.3s ease'
        }} />
      </div>
    </div>
  )
}

function Dashboard({ token, onLogout }) {
  const { get } = useApi(token)
  const [stats, setStats] = useState(null)
  const [anomalies, setAnomalies] = useState([])
  const [traces, setTraces] = useState([])
  const [infra, setInfra] = useState([])
  const [tab, setTab] = useState('anomalies')
  const [lastUpdate, setLastUpdate] = useState(null)

  const refresh = useCallback(async () => {
    try {
      const [s, a, t, i] = await Promise.all([
        get('/stats'),
        get('/anomalies?limit=20'),
        get('/traces?limit=20'),
        get('/infra?limit=10')
      ])
      setStats(s)
      setAnomalies(a)
      setTraces(t)
      setInfra(i)
      setLastUpdate(new Date())
    } catch (e) {
      if (e.message === '401') onLogout()
    }
  }, [get, onLogout])

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, 30000)
    return () => clearInterval(interval)
  }, [refresh])

  const latestInfra = infra[0]

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <div style={{
        borderBottom: '1px solid var(--border)',
        padding: '0 32px',
        display: 'flex', alignItems: 'center',
        justifyContent: 'space-between', height: 52
      }}>
        <div style={{
          fontFamily: 'var(--font-display)', fontWeight: 800,
          fontSize: 16, color: 'var(--amber)', letterSpacing: '-0.5px'
        }}>
          SENTINELOPS
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
          <div style={{ color: 'var(--text-dim)', fontSize: 11 }}>
            {lastUpdate ? `updated ${lastUpdate.toLocaleTimeString()}` : 'loading...'}
          </div>
          <div style={{
            width: 7, height: 7, borderRadius: '50%',
            background: 'var(--green)',
            animation: 'pulse 2s infinite'
          }} />
          <button onClick={onLogout} style={{
            background: 'none', border: '1px solid var(--border)',
            color: 'var(--text-dim)', padding: '4px 12px',
            fontFamily: 'var(--font-mono)', fontSize: 11,
            cursor: 'pointer'
          }}>logout</button>
        </div>
      </div>

      <div style={{ padding: '32px', flex: 1 }}>
        <div className="fade-in" style={{ display: 'flex', gap: 16, marginBottom: 32 }}>
          <StatCard label="total traces" value={stats?.total_traces?.toLocaleString()} />
          <StatCard label="anomalies detected" value={stats?.total_anomalies} accent="var(--amber)" />
          <StatCard label="avg latency (1h)" value={stats ? `${stats.avg_latency_ms}ms` : null} accent={stats?.avg_latency_ms > 1000 ? 'var(--red)' : 'var(--green)'} />
          {latestInfra && (
            <StatCard label="cpu" value={`${latestInfra.cpu_percent}%`} accent={latestInfra.cpu_percent > 90 ? 'var(--red)' : 'var(--green)'} />
          )}
        </div>

        <div style={{ display: 'flex', gap: 0, marginBottom: 20, borderBottom: '1px solid var(--border)' }}>
          {['anomalies', 'traces', 'infrastructure'].map(t => (
            <button key={t} onClick={() => setTab(t)} style={{
              background: 'none',
              borderBottom: tab === t ? '2px solid var(--amber)' : '2px solid transparent',
              border: 'none',
              borderBottom: tab === t ? '2px solid var(--amber)' : '2px solid transparent',
              color: tab === t ? 'var(--amber)' : 'var(--text-dim)',
              padding: '10px 20px', fontFamily: 'var(--font-mono)',
              fontSize: 12, cursor: 'pointer',
              textTransform: 'uppercase', letterSpacing: 1
            }}>
              {t === 'anomalies' ? `anomalies (${anomalies.length})` : t === 'traces' ? `traces (${traces.length})` : 'infrastructure'}
            </button>
          ))}
        </div>

        {tab === 'anomalies' && (
          <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {anomalies.length === 0 && (
              <div style={{ color: 'var(--text-dim)', padding: 24, textAlign: 'center' }}>
                no anomalies detected
              </div>
            )}
            {anomalies.map((a, i) => (
              <div key={i} style={{
                background: 'var(--bg-card)', border: '1px solid var(--border)',
                padding: '14px 20px', display: 'flex',
                alignItems: 'center', justifyContent: 'space-between',
                gap: 16
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 16, flex: 1 }}>
                  <SeverityBadge severity={a.severity} />
                  <div>
                    <div style={{ color: 'var(--text)', marginBottom: 2 }}>{a.metric_name}</div>
                    <div style={{ color: 'var(--text-dim)', fontSize: 11 }}>{a.service_name}</div>
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ color: 'var(--red)' }}>{a.actual_value.toFixed(0)}ms</div>
                  <div style={{ color: 'var(--text-dim)', fontSize: 11 }}>
                    expected {a.expected_value.toFixed(0)}ms
                  </div>
                </div>
                <div style={{ color: 'var(--text-muted)', fontSize: 11, minWidth: 140, textAlign: 'right' }}>
                  {new Date(a.timestamp).toLocaleTimeString()}
                </div>
              </div>
            ))}
          </div>
        )}

        {tab === 'traces' && (
          <div className="fade-in" style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            {traces.map((t, i) => (
              <div key={i} style={{
                background: 'var(--bg-card)', border: '1px solid var(--border)',
                padding: '12px 20px', display: 'flex',
                alignItems: 'center', justifyContent: 'space-between'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                  <div style={{
                    width: 6, height: 6, borderRadius: '50%',
                    background: t.duration_ms > 1000 ? 'var(--amber)' : 'var(--green)'
                  }} />
                  <div>
                    <div style={{ color: 'var(--text)' }}>{t.span_name}</div>
                    <div style={{ color: 'var(--text-dim)', fontSize: 11 }}>{t.service_name}</div>
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 32 }}>
                  <div style={{
                    color: t.duration_ms > 1000 ? 'var(--amber)' : 'var(--green)',
                    fontWeight: 700
                  }}>
                    {t.duration_ms}ms
                  </div>
                  <div style={{ color: 'var(--text-muted)', fontSize: 11, minWidth: 140, textAlign: 'right' }}>
                    {new Date(t.timestamp).toLocaleTimeString()}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {tab === 'infrastructure' && (
          <div className="fade-in">
            {infra.length === 0 ? (
              <div style={{ color: 'var(--text-dim)', padding: 24, textAlign: 'center' }}>
                no infrastructure data — install sentinelops SDK to collect metrics
              </div>
            ) : (
              <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap' }}>
                {infra.slice(0, 6).map((item, i) => (
                  <div key={i} style={{
                    background: 'var(--bg-card)', border: '1px solid var(--border)',
                    padding: '24px', flex: '1 1 300px'
                  }}>
                    <div style={{ color: 'var(--text-dim)', fontSize: 11, marginBottom: 16, textTransform: 'uppercase', letterSpacing: 1 }}>
                      {item.service_name} — {new Date(item.timestamp).toLocaleTimeString()}
                    </div>
                    <InfraBar label="CPU" value={item.cpu_percent} />
                    <InfraBar label="Memory" value={item.memory_percent} />
                    <InfraBar label="Disk" value={item.disk_percent} />
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default function App() {
  const [token, setToken] = useState(() => localStorage.getItem('sentinel_token'))

  const handleLogin = (t) => {
    localStorage.setItem('sentinel_token', t)
    setToken(t)
  }

  const handleLogout = () => {
    localStorage.removeItem('sentinel_token')
    setToken(null)
  }

  if (!token) return <Login onLogin={handleLogin} />
  return <Dashboard token={token} onLogout={handleLogout} />
}