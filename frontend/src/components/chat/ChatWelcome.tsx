import React, { useCallback, useEffect, useState } from 'react'
import { ArrowUpRight, BrainCircuit, Compass, FileCode2, GitBranchPlus, MessagesSquare } from 'lucide-react'

interface ModeAction {
  key: string
  placeholder: string
  guide: string
  label: string
  desc?: string
}

interface ModeEntry extends ModeAction {
  command: string
  icon: React.ReactNode
}

interface ChatWelcomeProps {
  onSelectMode: (mode: ModeAction) => void
}

const ACTIONS: ModeEntry[] = [
  {
    label: '规划学习路径',
    desc: '制定个性化的阶段目标和节奏',
    command: 'tutor.plan_path()',
    key: 'path',
    placeholder: '请描述你的 Python 基础和学习目标',
    guide: '好的，我来为你规划个性化的 Python 学习路径。请告诉我你的基础情况和想达到的目标。',
    icon: <Compass style={{ width: 16, height: 16 }} />,
  },
  {
    label: '提问答疑',
    desc: '快速解释概念、报错或代码逻辑',
    command: 'tutor.ask()',
    key: 'qa',
    placeholder: '请输入你的 Python 问题',
    guide: '好的，我来帮你解答 Python 问题。请在下方输入你的疑问。',
    icon: <MessagesSquare style={{ width: 16, height: 16 }} />,
  },
  {
    label: '生成练习题',
    desc: '围绕当前知识点做针对性训练',
    command: 'tutor.quiz()',
    key: 'quiz',
    placeholder: '请输入你想练习的知识点',
    guide: '好的，我来为你生成针对性的练习题。请告诉我你想练习哪个知识点。',
    icon: <FileCode2 style={{ width: 16, height: 16 }} />,
  },
  {
    label: '思维导图',
    desc: '把知识结构整理成可视化地图',
    command: 'tutor.mindmap()',
    key: 'mindmap',
    placeholder: '请输入你想梳理的知识主题',
    guide: '好的，我来为你创建知识思维导图。请输入你想梳理的主题。',
    icon: <GitBranchPlus style={{ width: 16, height: 16 }} />,
  },
  {
    label: '交互式学习',
    desc: '通过提问引导你自己想明白',
    command: 'tutor.socratic()',
    key: 'socratic',
    placeholder: '描述你想学习的知识点，AI 将通过提问引导你思考',
    guide: '好的，进入交互式学习模式。请告诉我你想学习哪个知识点，我会通过提问引导你思考。',
    icon: <BrainCircuit style={{ width: 16, height: 16 }} />,
  },
]

type REPLLine = { kind: 'prompt' | 'output'; text: string }

const REPL_LINES: REPLLine[] = [
  { kind: 'prompt', text: 'from tutor import mission_control' },
  { kind: 'prompt', text: 'mission_control.focus(topic="python")' },
  { kind: 'output', text: '"Ready. Choose a learning route to begin."' },
]

const TYPE_DELAY = 32
const LINE_PAUSE = 380

const ChatWelcome: React.FC<ChatWelcomeProps> = ({ onSelectMode }) => {
  const reduceMotion =
    typeof window !== 'undefined' &&
    window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches

  const [revealedLines, setRevealedLines] = useState<number>(reduceMotion ? REPL_LINES.length : 0)
  const [typedChars, setTypedChars] = useState<number>(reduceMotion ? REPL_LINES[REPL_LINES.length - 1].text.length : 0)

  useEffect(() => {
    if (revealedLines >= REPL_LINES.length) return
    const line = REPL_LINES[revealedLines].text

    if (typedChars < line.length) {
      const jitter = reduceMotion ? 0 : Math.random() * 24
      const timer = setTimeout(() => setTypedChars((value) => value + 1), TYPE_DELAY + jitter)
      return () => clearTimeout(timer)
    }

    const timer = setTimeout(() => {
      setRevealedLines((value) => value + 1)
      setTypedChars(0)
    }, LINE_PAUSE)

    return () => clearTimeout(timer)
  }, [revealedLines, typedChars, reduceMotion])

  const animationComplete = revealedLines >= REPL_LINES.length

  const handleClick = useCallback(
    (action: ModeEntry) => {
      onSelectMode({
        key: action.key,
        placeholder: action.placeholder,
        guide: action.guide,
        label: action.label,
      })
    },
    [onSelectMode],
  )

  return (
    <div className="chat-welcome-shell">
      <section className="chat-hero-card" style={{ borderRadius: 28, padding: '30px 28px' }}>
        <div
          className="shell-title-eyebrow"
          style={{
            color: 'var(--py-blue-deep)',
            background: 'rgba(48, 105, 152, 0.08)',
            border: '1px solid rgba(48, 105, 152, 0.14)',
            marginBottom: 18,
          }}
        >
          <span style={{ color: 'var(--py-yellow-deep)' }}>{'>>>'}</span>
          python mission control
        </div>

        <h1
          style={{
            margin: 0,
            fontFamily: 'var(--font-display)',
            fontSize: 'clamp(34px, 5vw, 54px)',
            lineHeight: 0.94,
            letterSpacing: '-0.05em',
            color: 'var(--ink)',
          }}
        >
          让学习像
          <br />
          操作一台 Python 工作站
        </h1>

        <p
          style={{
            maxWidth: 520,
            margin: '18px 0 0',
            color: 'var(--mute)',
            fontSize: 15,
            lineHeight: 1.8,
          }}
        >
          这里不是单纯聊天框，而是把提问、练习、路径规划、知识结构和进度反馈编排进同一条学习流里。
        </p>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: 12, marginTop: 24 }}>
          {[
            ['对话', '即时答疑与解释'],
            ['练习', '围绕知识点训练'],
            ['路径', '按阶段推进学习'],
          ].map(([title, desc]) => (
            <div
              key={title}
              style={{
                borderRadius: 18,
                padding: '14px 14px 12px',
                background: 'rgba(255,255,255,0.62)',
                border: '1px solid rgba(112, 137, 175, 0.16)',
              }}
            >
              <div style={{ color: 'var(--ink)', fontSize: 16, fontWeight: 700 }}>{title}</div>
              <div style={{ color: 'var(--mute)', fontSize: 12, lineHeight: 1.7, marginTop: 4 }}>{desc}</div>
            </div>
          ))}
        </div>

        <div style={{ marginTop: 24 }}>
          <div
            style={{
              width: '100%',
              maxWidth: 580,
              background: '#0f172a',
              borderRadius: 22,
              boxShadow: '0 30px 60px rgba(15, 23, 42, 0.26)',
              overflow: 'hidden',
              fontFamily: 'var(--font-mono)',
            }}
            aria-label="Python REPL 欢迎提示"
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 10,
                padding: '12px 16px',
                background: '#182235',
                borderBottom: '1px solid rgba(255, 255, 255, 0.06)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#ef4444' }} />
                <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#f5c518' }} />
                <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#10b981' }} />
              </div>
              <span style={{ color: '#8ea0c0', fontSize: 11 }}>learning session.py</span>
            </div>

            <div style={{ padding: '18px 20px 20px', fontSize: 13.5, lineHeight: 1.8, minHeight: 156 }}>
              {REPL_LINES.slice(0, revealedLines).map((line, index) => (
                <div key={index} style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
                  <span
                    style={{
                      width: 24,
                      flexShrink: 0,
                      color: line.kind === 'output' ? 'transparent' : 'var(--py-yellow)',
                      fontWeight: 700,
                    }}
                  >
                    {line.kind === 'output' ? '.' : '>>>'}
                  </span>
                  <span style={{ color: line.kind === 'output' ? 'var(--py-yellow)' : '#e6edf8' }}>{line.text}</span>
                </div>
              ))}

              {revealedLines < REPL_LINES.length && (
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
                  <span
                    style={{
                      width: 24,
                      flexShrink: 0,
                      color: REPL_LINES[revealedLines].kind === 'output' ? 'transparent' : 'var(--py-yellow)',
                      fontWeight: 700,
                    }}
                  >
                    {REPL_LINES[revealedLines].kind === 'output' ? '.' : '>>>'}
                  </span>
                  <span style={{ color: REPL_LINES[revealedLines].kind === 'output' ? 'var(--py-yellow)' : '#e6edf8' }}>
                    {REPL_LINES[revealedLines].text.slice(0, typedChars)}
                    <span className="repl-cursor" style={{ background: 'var(--py-yellow)' }} />
                  </span>
                </div>
              )}

              {animationComplete && (
                <div style={{ display: 'flex', alignItems: 'baseline', gap: 10 }}>
                  <span style={{ width: 24, flexShrink: 0, color: 'var(--py-yellow)', fontWeight: 700 }}>{'>>>'}</span>
                  <span className="repl-cursor" style={{ background: 'var(--py-yellow)' }} />
                </div>
              )}
            </div>
          </div>
        </div>
      </section>

      <section style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        <div className="chat-hero-card" style={{ borderRadius: 28, padding: '24px 22px' }}>
          <div style={{ color: 'var(--ink)', fontSize: 20, fontWeight: 700, marginBottom: 8 }}>选择一种学习入口</div>
          <p style={{ margin: 0, color: 'var(--mute)', fontSize: 13, lineHeight: 1.8 }}>
            参考优秀产品的思路，我们把高频动作做成“任务入口”，让第一次进入页面时就知道下一步该做什么。
          </p>
        </div>

        <div className="chat-action-grid">
          {ACTIONS.map((action) => (
            <button
              key={action.label}
              onClick={() => handleClick(action)}
              tabIndex={animationComplete ? 0 : -1}
              className="chat-action-card btn-click-feedback"
              style={{
                opacity: animationComplete ? 1 : 0,
                transform: animationComplete ? 'translateY(0)' : 'translateY(8px)',
                transitionDelay: animationComplete ? '60ms' : '0ms',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10 }}>
                <div
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: 34,
                    height: 34,
                    borderRadius: 12,
                    background: 'linear-gradient(135deg, rgba(48,105,152,0.14), rgba(255,212,59,0.18))',
                    color: 'var(--py-blue)',
                  }}
                >
                  {action.icon}
                </div>
                <ArrowUpRight style={{ width: 15, height: 15, color: 'var(--faint)' }} />
              </div>

              <code
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 11.5,
                  color: 'var(--py-blue)',
                  display: 'flex',
                  alignItems: 'baseline',
                  gap: 4,
                }}
              >
                <span style={{ color: 'var(--py-yellow-deep)', fontWeight: 700 }}>{'>>>'}</span>
                {action.command}
              </code>

              <div style={{ color: 'var(--ink)', fontSize: 15, fontWeight: 700 }}>{action.label}</div>
              <div style={{ color: 'var(--mute)', fontSize: 12, lineHeight: 1.7 }}>{action.desc}</div>
            </button>
          ))}
        </div>
      </section>
    </div>
  )
}

export default ChatWelcome
