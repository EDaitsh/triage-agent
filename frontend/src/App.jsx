import { useState, useEffect, useRef, useCallback } from 'react'

const FINAL_STATES = new Set(['completed', 'rejected', 'error'])

const STATE_LABELS = {
  created: 'נוצר',
  routing: 'מנתב...',
  working_attempt_1: 'עובד (ניסיון 1)...',
  working_attempt_2: 'עובד (ניסיון 2)...',
  evaluating: 'מעריך...',
  pending_approval: 'ממתין לאישור',
  approved: 'אושר',
  rejected: 'נדחה',
  completed: 'הושלם',
  error: 'שגיאה',
}

const CATEGORY_LABELS = {
  support: 'תמיכה',
  bug: 'באג',
  inquiry: 'פנייה',
  spam: 'ספאם',
  urgent_human: 'דחוף – אנושי',
}

function useTaskPolling(setTasks) {
  const intervals = useRef({})

  const startPolling = useCallback(
    (taskId) => {
      if (intervals.current[taskId]) return
      intervals.current[taskId] = setInterval(async () => {
        try {
          const res = await fetch(`/tasks/${taskId}`)
          if (!res.ok) return
          const data = await res.json()
          setTasks((prev) =>
            prev.map((t) => (t.task_id === taskId ? { ...t, ...data, task_id: taskId } : t)),
          )
          if (FINAL_STATES.has(data.state)) {
            clearInterval(intervals.current[taskId])
            delete intervals.current[taskId]
          }
        } catch {
          // ignore transient errors
        }
      }, 2000)
    },
    [setTasks],
  )

  useEffect(() => {
    return () => Object.values(intervals.current).forEach(clearInterval)
  }, [])

  return startPolling
}

// ── RAG Panel ──────────────────────────────────────────────────────────────────
function RagPanel() {
  const [activeTab, setActiveTab] = useState('ingest')
  // Ingest state
  const [ingestText, setIngestText] = useState('')
  const [ingestSource, setIngestSource] = useState('manual')
  const [ingestResult, setIngestResult] = useState(null)
  const [ingestLoading, setIngestLoading] = useState(false)
  const [ingestError, setIngestError] = useState('')
  const [clearLoading, setClearLoading] = useState(false)
  const [clearMsg, setClearMsg] = useState('')
  // Query state
  const [question, setQuestion] = useState('')
  const [queryResult, setQueryResult] = useState(null)
  const [queryLoading, setQueryLoading] = useState(false)
  const [queryError, setQueryError] = useState('')
  // Evals state
  const [evalText, setEvalText] = useState('')
  const [evalN, setEvalN] = useState(5)
  const [evalResult, setEvalResult] = useState(null)
  const [evalLoading, setEvalLoading] = useState(false)
  const [evalError, setEvalError] = useState('')

  async function handleClear() {
    if (!window.confirm('למחוק את כל ה-chunks מהמאגר?')) return
    setClearLoading(true)
    setClearMsg('')
    try {
      const res = await fetch('/rag/clear', { method: 'DELETE' })
      if (!res.ok) throw new Error(`שגיאת שרת: ${res.status}`)
      setClearMsg('המאגר נוקה בהצלחה')
      setIngestResult(null)
    } catch (err) {
      setClearMsg(`שגיאה: ${err.message}`)
    } finally {
      setClearLoading(false)
    }
  }

  async function handleIngest(e) {
    e.preventDefault()
    if (!ingestText.trim()) return
    setIngestLoading(true)
    setIngestError('')
    setIngestResult(null)
    try {
      const res = await fetch('/rag/ingest', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: ingestText, source: ingestSource || 'manual' }),
      })
      if (!res.ok) throw new Error(`שגיאת שרת: ${res.status}`)
      setIngestResult(await res.json())
    } catch (err) {
      setIngestError(err.message)
    } finally {
      setIngestLoading(false)
    }
  }

  async function handleQuery(e) {
    e.preventDefault()
    if (!question.trim()) return
    setQueryLoading(true)
    setQueryError('')
    setQueryResult(null)
    try {
      const res = await fetch('/rag/query', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      })
      if (!res.ok) throw new Error(`שגיאת שרת: ${res.status}`)
      setQueryResult(await res.json())
    } catch (err) {
      setQueryError(err.message)
    } finally {
      setQueryLoading(false)
    }
  }

  async function handleEvals(e) {
    e.preventDefault()
    if (!evalText.trim()) return
    setEvalLoading(true)
    setEvalError('')
    setEvalResult(null)
    try {
      const res = await fetch('/rag/evals', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: evalText, n_questions: evalN }),
      })
      if (!res.ok) throw new Error(`שגיאת שרת: ${res.status}`)
      setEvalResult(await res.json())
    } catch (err) {
      setEvalError(err.message)
    } finally {
      setEvalLoading(false)
    }
  }

  return (
    <div className="rag-panel">
      <div className="rag-tabs">
        {[['ingest', '📥 הכנסת מסמך'], ['query', '🔍 שאילתה'], ['evals', '📊 הערכה']].map(
          ([id, label]) => (
            <button
              key={id}
              className={`rag-tab${activeTab === id ? ' active' : ''}`}
              onClick={() => setActiveTab(id)}
            >
              {label}
            </button>
          ),
        )}
      </div>

      {/* ── Ingest ── */}
      {activeTab === 'ingest' && (
        <form onSubmit={handleIngest} className="rag-form">
          <label className="rag-label">שם מקור</label>
          <input
            className="rag-input"
            value={ingestSource}
            onChange={(e) => setIngestSource(e.target.value)}
            placeholder="לדוגמה: company_knowledge"
          />
          <label className="rag-label">תוכן המסמך</label>
          <textarea
            className="rag-textarea"
            rows={8}
            value={ingestText}
            onChange={(e) => setIngestText(e.target.value)}
            placeholder="הדביקו את תוכן המסמך הארגוני כאן..."
            disabled={ingestLoading}
          />
          <button className="rag-btn" type="submit" disabled={ingestLoading || !ingestText.trim()}>
            {ingestLoading ? 'מעבד...' : 'הכנס למאגר'}
          </button>
          <button
            type="button"
            className="rag-btn rag-btn-danger"
            onClick={handleClear}
            disabled={clearLoading}
          >
            {clearLoading ? 'מנקה...' : '🗑 נקה מאגר'}
          </button>
          {clearMsg && <p className="rag-clear-msg">{clearMsg}</p>}
          {ingestError && <p className="rag-error">{ingestError}</p>}
          {ingestResult && (
            <div className="rag-result">
              <span className="badge badge-success">✓ נוסף בהצלחה</span>{' '}
              {ingestResult.chunks_added} chunks מ-{ingestResult.source}
            </div>
          )}
        </form>
      )}

      {/* ── Query ── */}
      {activeTab === 'query' && (
        <form onSubmit={handleQuery} className="rag-form">
          <label className="rag-label">שאלה</label>
          <textarea
            className="rag-textarea"
            rows={3}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="שאלו שאלה על המידע הארגוני..."
            disabled={queryLoading}
          />
          <button className="rag-btn" type="submit" disabled={queryLoading || !question.trim()}>
            {queryLoading ? 'מחפש...' : 'שאל את ה-RAG'}
          </button>
          {queryError && <p className="rag-error">{queryError}</p>}
          {queryResult && (
            <div className="rag-answer">
              <p className="rag-answer-text">{queryResult.answer}</p>
              {queryResult.sources?.length > 0 && (
                <details className="rag-sources">
                  <summary>מקורות ({queryResult.sources.length})</summary>
                  {queryResult.sources.map((s, i) => (
                    <div key={i} className="rag-source-item">
                      <span className="rag-source-label">{s.source}</span>
                      <p>{s.text}</p>
                    </div>
                  ))}
                </details>
              )}
            </div>
          )}
        </form>
      )}

      {/* ── Evals ── */}
      {activeTab === 'evals' && (
        <form onSubmit={handleEvals} className="rag-form">
          <label className="rag-label">מסמך לבדיקה</label>
          <textarea
            className="rag-textarea"
            rows={7}
            value={evalText}
            onChange={(e) => setEvalText(e.target.value)}
            placeholder="הדביקו מסמך – המערכת תייצר שאלות ותעריך את ה-RAG אוטומטית..."
            disabled={evalLoading}
          />
          <div className="rag-inline">
            <label className="rag-label">מספר שאלות</label>
            <input
              type="number"
              min={1}
              max={20}
              className="rag-input rag-input-sm"
              value={evalN}
              onChange={(e) => setEvalN(Number(e.target.value))}
            />
          </div>
          <button className="rag-btn" type="submit" disabled={evalLoading || !evalText.trim()}>
            {evalLoading ? 'מריץ הערכה...' : 'הרץ Evals'}
          </button>
          {evalError && <p className="rag-error">{evalError}</p>}
          {evalResult && (
            <div className="rag-eval-results">
              <div className="rag-eval-summary">
                <span>שאלות: {evalResult.n_questions}</span>
                <span
                  className={`badge ${evalResult.avg_score >= 0.7 ? 'badge-success' : evalResult.avg_score >= 0.4 ? 'badge-warning' : 'badge-error'}`}
                >
                  ציון ממוצע: {(evalResult.avg_score * 100).toFixed(0)}%
                </span>
              </div>
              {evalResult.results.map((r, i) => (
                <div key={i} className="rag-eval-item">
                  <div className="rag-eval-header">
                    <span className="rag-eval-q">שאלה {i + 1}: {r.question}</span>
                    <span
                      className={`badge ${r.score >= 0.7 ? 'badge-success' : r.score >= 0.4 ? 'badge-warning' : 'badge-error'}`}
                    >
                      {(r.score * 100).toFixed(0)}%
                    </span>
                  </div>
                  <p className="rag-eval-meta">
                    <strong>צפוי:</strong> {r.expected_answer}
                  </p>
                  <p className="rag-eval-meta">
                    <strong>בפועל:</strong> {r.actual_answer}
                  </p>
                  <p className="rag-eval-reasoning">💬 {r.reasoning}</p>
                </div>
              ))}
            </div>
          )}
        </form>
      )}
    </div>
  )
}

export default function App() {
  const [appTab, setAppTab] = useState('agent')
  const [message, setMessage] = useState('')
  const [tasks, setTasks] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const startPolling = useTaskPolling(setTasks)

  async function handleSubmit(e) {
    e.preventDefault()
    const text = message.trim()
    if (!text) return
    setLoading(true)
    setError('')
    try {
      const res = await fetch('/message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
      })
      if (!res.ok) throw new Error(`שגיאת שרת: ${res.status}`)
      const { task_id } = await res.json()
      setTasks((prev) => [{ task_id, state: 'created', message: text }, ...prev])
      setMessage('')
      startPolling(task_id)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleApprove(taskId) {
    await fetch(`/tasks/${taskId}/approve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
  }

  async function handleReject(taskId, comment) {
    await fetch(`/tasks/${taskId}/reject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ comment }),
    })
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>🤖 Triage Agent</h1>
        <p>מערכת טריאז' חכמה לניתוב פניות</p>
      </header>

      <div className="app-nav">
        <button
          className={`nav-tab${appTab === 'agent' ? ' active' : ''}`}
          onClick={() => setAppTab('agent')}
        >
          🤖 Agent
        </button>
        <button
          className={`nav-tab${appTab === 'rag' ? ' active' : ''}`}
          onClick={() => setAppTab('rag')}
        >
          📚 מאגר ידע (RAG)
        </button>
      </div>

      <main className="app-main">
        {appTab === 'agent' && (
          <>
            <form onSubmit={handleSubmit} className="message-form">
              <textarea
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="הקלידו את ההודעה כאן..."
                rows={4}
                disabled={loading}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && e.ctrlKey) handleSubmit(e)
                }}
              />
              <div className="form-footer">
                <span className="hint">Ctrl+Enter לשליחה</span>
                <button type="submit" disabled={loading || !message.trim()}>
                  {loading ? 'שולח...' : 'שלח הודעה'}
                </button>
              </div>
              {error && <p className="error-msg">{error}</p>}
            </form>

            <div className="tasks-list">
              {tasks.length === 0 && (
                <div className="empty-state">אין משימות עדיין – שלחו הודעה ראשונה</div>
              )}
              {tasks.map((task) => (
                <TaskCard
                  key={task.task_id}
                  task={task}
                  onApprove={handleApprove}
                  onReject={handleReject}
                />
              ))}
            </div>
          </>
        )}

        {appTab === 'rag' && <RagPanel />}
      </main>
    </div>
  )
}

function TaskCard({ task, onApprove, onReject }) {
  const [rejectComment, setRejectComment] = useState('')
  const [showRejectForm, setShowRejectForm] = useState(false)

  const isActive = !FINAL_STATES.has(task.state) && task.state !== 'pending_approval'
  const isPending = task.state === 'pending_approval'

  return (
    <div className={`task-card state-${task.state}`}>
      {/* Header */}
      <div className="task-header">
        <span className="task-id">{task.task_id}</span>
        <span className={`state-badge state-${task.state}`}>
          {isActive && <span className="spinner" />}
          {STATE_LABELS[task.state] ?? task.state}
        </span>
      </div>

      {/* Original message */}
      {task.message && <blockquote className="task-message">"{task.message}"</blockquote>}

      {/* Router */}
      {task.router && (
        <div className="card-section">
          <span className="section-label">ניתוב</span>
          <span className="category-badge">
            {CATEGORY_LABELS[task.router.category] ?? task.router.category}
          </span>
          {task.router.requires_human && (
            <span className="badge badge-warning">דורש טיפול אנושי</span>
          )}
        </div>
      )}

      {/* Worker output */}
      {task.worker_output && (
        <div className="card-section">
          <span className="section-label">תגובה</span>
          <pre className="result-text">{task.worker_output.result}</pre>
          {task.worker_output.missing_details?.length > 0 && (
            <div className="missing-details">
              <span className="section-label">פרטים חסרים</span>
              <ul>
                {task.worker_output.missing_details.map((d, i) => (
                  <li key={i}>{d}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      {/* Evaluator */}
      {task.evaluator && (
        <div className="card-section evaluator-section">
          <span className="section-label">הערכה</span>
          <span className={`badge ${task.evaluator.passed ? 'badge-success' : 'badge-error'}`}>
            {task.evaluator.passed ? '✓ עבר' : '✗ נכשל'}
          </span>
          {task.evaluator.feedback && (
            <p className="evaluator-feedback">{task.evaluator.feedback}</p>
          )}
        </div>
      )}

      {/* HITL approval */}
      {isPending && (
        <div className="approval-section">
          <p className="approval-notice">⏳ ממתין לאישור אנושי לפני שליחה</p>
          <div className="approval-buttons">
            <button className="btn-approve" onClick={() => onApprove(task.task_id)}>
              ✓ אשר
            </button>
            <button
              className="btn-reject"
              onClick={() => setShowRejectForm((v) => !v)}
            >
              ✗ דחה
            </button>
          </div>
          {showRejectForm && (
            <div className="reject-form">
              <input
                value={rejectComment}
                onChange={(e) => setRejectComment(e.target.value)}
                placeholder="סיבת הדחייה (אופציונלי)"
              />
              <button
                className="btn-reject-confirm"
                onClick={() => onReject(task.task_id, rejectComment)}
              >
                אשר דחייה
              </button>
            </div>
          )}
        </div>
      )}

      {/* Final state banners */}
      {task.state === 'completed' && (
        <div className="final-banner banner-success">✅ הושלם בהצלחה</div>
      )}
      {task.state === 'rejected' && (
        <div className="final-banner banner-rejected">
          ❌ נדחה{task.approval_comment ? ` – ${task.approval_comment}` : ''}
        </div>
      )}
      {task.state === 'error' && (
        <div className="final-banner banner-error">⚠️ שגיאה: {task.error}</div>
      )}
    </div>
  )
}
