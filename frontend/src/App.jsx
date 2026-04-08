import { useState, useEffect, useCallback } from 'react'

const API = '/api'

function useApi(token) {
  const get = useCallback(async (path) => {
    const res = await fetch(`${API}${path}`, {
      headers: { Authorization: `Bearer ${token}` }
    })
    if (!res.ok) throw new Error(String(res.status))
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
      if (!res.ok) {
        setError('Invalid credentials')
        setLoading(false)
        return
      }
      const data = await res.json()
      onLogin(data.access_token)
    } catch {
      setError('Connection error')
      setLoading(false)
    }
  }

  return (
    <div className="login-wrap">
      <div className="login-card panel-strong fade-in">
        <div className="login-hero">
          <div className="display-title login-brand">SENTINELOPS</div>
          <div className="login-kicker">
            Observability platform for teams that need the signal, not just the noise.
          </div>
        </div>

        <div className="login-fields">
          <input
            type="email"
            placeholder="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submit()}
            className="input-field"
          />
          <input
            type="password"
            placeholder="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submit()}
            className="input-field"
          />
          {error && <div className="error-text">{error}</div>}
          <button onClick={submit} disabled={loading} className="login-button">
            {loading ? 'Connecting...' : 'Login →'}
          </button>
        </div>
      </div>
    </div>
  )
}

function StatCard({ label, value, accent, hint }) {
  return (
    <div className="panel metric-card fade-in">
      <div className="metric-label">{label}</div>
      <div className="metric-value" style={{ color: accent || 'var(--text)' }}>{value ?? '—'}</div>
      {hint && <div className="metric-hint">{hint}</div>}
    </div>
  )
}

function SeverityBadge({ severity }) {
  const className = severity === 'critical' ? 'pill pill-critical' : 'pill pill-warning'
  return <span className={className}>{severity}</span>
}

function InfraBar({ label, value }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <span className="section-subtitle">{label}</span>
        <span style={{ color: value > 90 ? 'var(--red)' : value > 70 ? 'var(--amber)' : 'var(--green)', fontFamily: 'var(--font-mono)', fontWeight: 700, fontSize: 13 }}>
          {value}%
        </span>
      </div>
      <div style={{ background: 'rgba(255,255,255,0.05)', height: 8, width: '100%', borderRadius: 999, overflow: 'hidden' }}>
        <div
          style={{
            height: 8,
            width: `${Math.max(0, Math.min(100, value))}%`,
            borderRadius: 999,
            background: value > 90
              ? 'linear-gradient(90deg, #fb7185, #f97316)'
              : value > 70
                ? 'linear-gradient(90deg, #f59e0b, #fbbf24)'
                : 'linear-gradient(90deg, #38bdf8, #34d399)'
          }}
        />
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
  const [containers, setContainers] = useState([])
  const [tab, setTab] = useState('anomalies')
  const [lastUpdate, setLastUpdate] = useState(null)

  const refresh = useCallback(async () => {
    try {
      const [s, a, t, i, c] = await Promise.all([
        get('/stats'),
        get('/anomalies?limit=20'),
        get('/traces?limit=20'),
        get('/infra?limit=10'),
        get('/containers?limit=20')
      ])
      setStats(s)
      setAnomalies(a)
      setTraces(t)
      setInfra(i)
      setContainers(c)
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
    <div className="shell">
      <div className="topbar">
        <div className="brand-mark">
          <div className="brand-badge" />
          <div>
            <div className="brand-text">SENTINELOPS</div>
            <div className="compact-note">Observability platform</div>
          </div>
        </div>

        <div className="topbar-meta">
          <div className="pill pill-ok">live</div>
          <div className="compact-note">{lastUpdate ? `updated ${lastUpdate.toLocaleTimeString()}` : 'loading...'}</div>
          <div className="status-dot" />
          <button onClick={onLogout} className="ghost-button">logout</button>
        </div>
      </div>

      <div className="page">
        <div className="hero-grid fade-in">
          <div className="hero-copy panel-strong">
            <div className="eyebrow">Real-time observability for small teams</div>
            <h1>See traces, containers, and infra in one place.</h1>
            <p>
              SentinelOps helps you spot slowdowns, correlate app traffic with container health,
              and keep an eye on the system without drowning in metrics.
            </p>
          </div>

          <div className="hero-side panel">
            <div className="section-title">Current pulse</div>
            <div className="hero-side-grid">
              <div className="hero-mini">
                <div className="hero-mini-label">Total traces</div>
                <div className="hero-mini-value">{stats?.total_traces?.toLocaleString() ?? '—'}</div>
              </div>
              <div className="hero-mini">
                <div className="hero-mini-label">Anomalies</div>
                <div className="hero-mini-value" style={{ color: 'var(--amber)' }}>{stats?.total_anomalies ?? '—'}</div>
              </div>
              <div className="hero-mini">
                <div className="hero-mini-label">Avg latency (1h)</div>
                <div className="hero-mini-value" style={{ color: stats?.avg_latency_ms > 1000 ? 'var(--red)' : 'var(--green)' }}>
                  {stats ? `${stats.avg_latency_ms}ms` : '—'}
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="metric-grid fade-in" style={{ marginBottom: 18 }}>
          <StatCard label="total traces" value={stats?.total_traces?.toLocaleString()} hint="Events ingested from the demo app and SDK" />
          <StatCard label="anomalies detected" value={stats?.total_anomalies} accent="var(--amber)" hint="Latency spikes across the tenant" />
          <StatCard label="avg latency (1h)" value={stats ? `${stats.avg_latency_ms}ms` : null} accent={stats?.avg_latency_ms > 1000 ? 'var(--red)' : 'var(--green)'} hint="Rolling average from ClickHouse" />
          <StatCard label="cpu" value={latestInfra ? `${latestInfra.cpu_percent}%` : null} accent={latestInfra?.cpu_percent > 90 ? 'var(--red)' : 'var(--green)'} hint="Latest app snapshot" />
        </div>

        <div className="panel section-card">
          <div className="section-head">
            <div>
              <div className="section-title">Workspace</div>
              <div className="section-subtitle">Live app traces, infra, and container snapshots</div>
            </div>
            <div className="tabs">
              {['anomalies', 'traces', 'infrastructure', 'containers'].map((t) => (
                <button
                  key={t}
                  onClick={() => setTab(t)}
                  className={`tab-button ${tab === t ? 'is-active' : ''}`}
                >
                  {t === 'anomalies'
                    ? `anomalies (${anomalies.length})`
                    : t === 'traces'
                      ? `traces (${traces.length})`
                      : t === 'containers'
                        ? `containers (${containers.length})`
                        : 'infrastructure'}
                </button>
              ))}
            </div>
          </div>

          <div className="section-body">
            {tab === 'anomalies' && (
              <div className="fade-in list-stack">
                {anomalies.length === 0 ? (
                  <div className="panel-soft" style={{ padding: 28, textAlign: 'center', borderRadius: 20 }}>
                    <div className="section-title" style={{ marginBottom: 8 }}>No anomalies yet</div>
                    <div className="muted">Generate a bigger latency spike if you want to test alerts.</div>
                  </div>
                ) : anomalies.map((a, i) => (
                  <div key={i} className="list-item">
                    <div style={{ display: 'flex', alignItems: 'center', gap: 14, flex: 1, minWidth: 0 }}>
                      <SeverityBadge severity={a.severity} />
                      <div style={{ minWidth: 0 }}>
                        <div style={{ fontSize: 17, fontWeight: 700, letterSpacing: '-0.03em' }}>{a.metric_name}</div>
                        <div className="compact-note">{a.service_name}</div>
                      </div>
                    </div>
                    <div style={{ textAlign: 'right', minWidth: 170 }}>
                      <div style={{ color: 'var(--text)', fontFamily: 'var(--font-display)', fontSize: 22, fontWeight: 800 }}>
                        {a.actual_value.toFixed(0)}ms
                      </div>
                      <div className="compact-note">Expected {a.expected_value.toFixed(0)}ms</div>
                    </div>
                    <div className="compact-note" style={{ minWidth: 140, textAlign: 'right' }}>
                      {new Date(a.timestamp).toLocaleTimeString()}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {tab === 'traces' && (
              <div className="fade-in list-stack">
                {traces.length === 0 ? (
                  <div className="panel-soft" style={{ padding: 28, textAlign: 'center', borderRadius: 20 }}>
                    <div className="section-title" style={{ marginBottom: 8 }}>No traces yet</div>
                    <div className="muted">Hit the demo app a few times to populate this view.</div>
                  </div>
                ) : traces.map((t, i) => (
                  <div key={i} className="list-item">
                    <div style={{ display: 'flex', alignItems: 'center', gap: 14, minWidth: 0 }}>
                      <div style={{
                        width: 12,
                        height: 12,
                        borderRadius: '50%',
                        background: t.duration_ms > 1000
                          ? 'linear-gradient(135deg, #f59e0b, #f97316)'
                          : 'linear-gradient(135deg, #38bdf8, #34d399)',
                        boxShadow: t.duration_ms > 1000
                          ? '0 0 0 6px rgba(245, 158, 11, 0.10)'
                          : '0 0 0 6px rgba(56, 189, 248, 0.10)'
                      }} />
                      <div style={{ minWidth: 0 }}>
                        <div style={{ fontSize: 16, fontWeight: 700, letterSpacing: '-0.03em' }}>{t.span_name}</div>
                        <div className="compact-note">{t.service_name}</div>
                      </div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
                      <div style={{
                        fontFamily: 'var(--font-display)',
                        fontSize: 22,
                        fontWeight: 800,
                        color: t.duration_ms > 1000 ? 'var(--amber)' : 'var(--green)'
                      }}>
                        {t.duration_ms}ms
                      </div>
                      <div className="compact-note" style={{ minWidth: 140, textAlign: 'right' }}>
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
                  <div className="panel-soft" style={{ padding: 28, textAlign: 'center', borderRadius: 20 }}>
                    <div className="section-title" style={{ marginBottom: 8 }}>No infrastructure data</div>
                    <div className="muted">Install the SDK in a service to collect CPU, memory, and disk metrics.</div>
                  </div>
                ) : (
                  <div style={{ display: 'grid', gap: 14, gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))' }}>
                    {infra.slice(0, 6).map((item, i) => (
                      <div key={i} className="panel-soft" style={{ padding: 22, borderRadius: 22 }}>
                        <div className="section-subtitle" style={{ marginBottom: 10 }}>{item.service_name}</div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
                          <div style={{ fontSize: 17, fontWeight: 700 }}>{new Date(item.timestamp).toLocaleTimeString()}</div>
                          <div className="pill pill-ok">live</div>
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

            {tab === 'containers' && (
              <div className="fade-in">
                {containers.length === 0 ? (
                  <div className="panel-soft" style={{ padding: 28, textAlign: 'center', borderRadius: 20 }}>
                    <div className="section-title" style={{ marginBottom: 8 }}>No container data</div>
                    <div className="muted">Mount the Docker socket and wait one collection cycle.</div>
                  </div>
                ) : (
                  <div className="list-stack">
                    {containers.map((item, i) => (
                      <div key={i} className="list-item">
                        <div style={{ minWidth: 280, flex: 1 }}>
                          <div style={{ fontSize: 17, fontWeight: 700, letterSpacing: '-0.03em' }}>
                            {item.container_name || item.container_id}
                          </div>
                          <div className="compact-note" style={{ marginTop: 6 }}>
                            {item.container_image || 'unknown image'} · {item.container_status || 'unknown status'}
                          </div>
                          <div className="compact-note" style={{ marginTop: 6, color: 'var(--text-dim)' }}>
                            {item.service_name}
                          </div>
                        </div>

                        <div style={{ flex: 1.2, minWidth: 0 }}>
                          <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(2, minmax(0, 1fr))' }}>
                            <InfraBar label="CPU" value={Math.min(Math.round(item.cpu_percent), 100)} />
                            <InfraBar label="Memory" value={Math.min(Math.round(item.memory_percent), 100)} />
                          </div>
                          <div style={{ display: 'grid', gap: 12, gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', marginTop: 12 }}>
                            <div className="hero-mini" style={{ padding: '14px 16px' }}>
                              <div className="hero-mini-label">RX</div>
                              <div className="hero-mini-value" style={{ fontSize: 20 }}>{item.network_rx_mb.toFixed(2)} MB</div>
                            </div>
                            <div className="hero-mini" style={{ padding: '14px 16px' }}>
                              <div className="hero-mini-label">TX</div>
                              <div className="hero-mini-value" style={{ fontSize: 20 }}>{item.network_tx_mb.toFixed(2)} MB</div>
                            </div>
                          </div>
                        </div>

                        <div className="compact-note" style={{ minWidth: 140, textAlign: 'right' }}>
                          {new Date(item.timestamp).toLocaleTimeString()}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export default function App() {
  const [token, setToken] = useState(() => localStorage.getItem('sentinel_token'))

  const handleLogin = (nextToken) => {
    localStorage.setItem('sentinel_token', nextToken)
    setToken(nextToken)
  }

  const handleLogout = () => {
    localStorage.removeItem('sentinel_token')
    setToken(null)
  }

  if (!token) return <Login onLogin={handleLogin} />
  return <Dashboard token={token} onLogout={handleLogout} />
}