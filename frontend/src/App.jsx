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

export default function App() {
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

      <main className="app-main">
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
