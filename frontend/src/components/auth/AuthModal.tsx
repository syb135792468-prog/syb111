import React, { useState, useCallback, useRef, useEffect } from 'react'
import { User, Lock, Eye, EyeOff, Sparkles } from 'lucide-react'

interface RingParticle {
  distance: number
  angle: number
  size: number
  alpha: number
  speed: number
  color: string
}

interface DustParticle {
  distance: number
  angle: number
  size: number
  alpha: number
  speed: number
}

interface BackgroundStar {
  x: number
  y: number
  size: number
  alpha: number
  twinkle: number
}

interface AuthResult {
  success: boolean
  message?: string
}

interface AuthStore {
  login: (username: string, password: string) => Promise<AuthResult>
  register: (username: string, password: string) => Promise<AuthResult>
}

interface ChatStore {
  loadConversations: () => void
}

interface AuthModalProps {
  authStore: AuthStore
  chatStore: ChatStore
}

const AuthModal: React.FC<AuthModalProps> = ({ authStore, chatStore }) => {
  const [activeTab, setActiveTab] = useState<'login' | 'register'>('login')
  const [loginUsername, setLoginUsername] = useState('')
  const [loginPassword, setLoginPassword] = useState('')
  const [regUsername, setRegUsername] = useState('')
  const [regPassword, setRegPassword] = useState('')
  const [loginError, setLoginError] = useState('')
  const [regError, setRegError] = useState('')
  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current!
    if (!canvas) return
    const ctx = canvas.getContext('2d')!
    if (!ctx) return

    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    const frameInterval = reduceMotion ? 1000 / 20 : 1000 / 30
    const startDelay = reduceMotion ? 0 : 120
    const TILT = 0.38

    let viewportWidth = window.innerWidth
    let viewportHeight = window.innerHeight
    let maxRadius = 0
    let ringParticles: RingParticle[] = []
    let outerParticles: DustParticle[] = []
    let bgStars: BackgroundStar[] = []
    let animId = 0
    let startTimer = 0
    let lastFrameTime = 0

    function createParticles() {
      const area = viewportWidth * viewportHeight
      const density = reduceMotion
        ? 0.28
        : area < 700000
          ? 0.45
          : area < 1400000
            ? 0.65
            : 0.85

      maxRadius = Math.min(viewportWidth, viewportHeight) * (viewportWidth < 768 ? 0.28 : 0.33)
      const baseRadius = Math.max(60, maxRadius * 0.35)
      const ringCount = Math.max(700, Math.floor(2600 * density))
      const dustCount = Math.max(180, Math.floor(700 * density))
      const starCount = Math.max(60, Math.floor(220 * density))

      ringParticles = []
      outerParticles = []
      bgStars = []

      for (let i = 0; i < ringCount; i++) {
        const distance = baseRadius + Math.random() * (maxRadius - baseRadius)
        const bright = Math.random() > 0.92
        const angle = Math.random() * Math.PI * 2
        let r: number, g: number, b: number
        if (bright) {
          // Python yellow sparks
          r = 255
          g = 212 + Math.random() * 30
          b = 59 + Math.random() * 40
        } else {
          // Python blue ring particles
          r = 60 + Math.random() * 50
          g = 110 + Math.random() * 40
          b = 160 + Math.random() * 30
        }
        ringParticles.push({
          distance,
          angle,
          size: bright ? 1.3 + Math.random() * 0.5 : 0.5 + Math.random() * 0.8,
          alpha: bright ? 0.7 + Math.random() * 0.22 : 0.16 + Math.random() * 0.3,
          speed: 0.00035 + (1 - distance / Math.max(maxRadius, 1)) * 0.001,
          color: `rgba(${r}, ${g}, ${b}, `,
        })
      }

      for (let i = 0; i < dustCount; i++) {
        outerParticles.push({
          distance: maxRadius * 0.7 + Math.random() * maxRadius * 0.65,
          angle: Math.random() * Math.PI * 2,
          size: 0.35 + Math.random() * 0.7,
          alpha: 0.08 + Math.random() * 0.2,
          speed: 0.00012 + Math.random() * 0.00025,
        })
      }

      for (let i = 0; i < starCount; i++) {
        bgStars.push({
          x: Math.random() * viewportWidth,
          y: Math.random() * viewportHeight,
          size: 0.4 + Math.random() * 0.9,
          alpha: 0.18 + Math.random() * 0.35,
          twinkle: Math.random() * Math.PI * 2,
        })
      }
    }

    function resize() {
      viewportWidth = window.innerWidth
      viewportHeight = window.innerHeight
      const dpr = Math.min(window.devicePixelRatio || 1, 1.25)
      canvas.width = Math.floor(viewportWidth * dpr)
      canvas.height = Math.floor(viewportHeight * dpr)
      canvas.style.width = `${viewportWidth}px`
      canvas.style.height = `${viewportHeight}px`
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      createParticles()
    }

    function drawFrame() {
      ctx.fillStyle = 'rgba(5, 7, 22, 0.18)'
      ctx.fillRect(0, 0, viewportWidth, viewportHeight)

      const centerX = viewportWidth * (viewportWidth < 768 ? 0.5 : 0.72)
      const centerY = viewportHeight * 0.5

      for (const star of bgStars) {
        star.twinkle += 0.015
        const opacity = star.alpha * (0.6 + Math.sin(star.twinkle) * 0.4)
        ctx.beginPath()
        ctx.arc(star.x, star.y, star.size, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(255, 255, 255, ${opacity})`
        ctx.fill()
      }

      ctx.globalCompositeOperation = 'lighter'

      for (const p of outerParticles) {
        p.angle += p.speed
        const x = centerX + Math.cos(p.angle) * p.distance
        const y = centerY + Math.sin(p.angle) * p.distance * TILT
        ctx.beginPath()
        ctx.arc(x, y, p.size, 0, Math.PI * 2)
        ctx.fillStyle = `rgba(160, 200, 230, ${p.alpha})`
        ctx.fill()
      }

      for (const p of ringParticles) {
        p.angle += p.speed
        const x = centerX + Math.cos(p.angle) * p.distance
        const y = centerY + Math.sin(p.angle) * p.distance * TILT
        ctx.beginPath()
        ctx.arc(x, y, p.size, 0, Math.PI * 2)
        ctx.fillStyle = p.color + p.alpha + ')'
        ctx.fill()
      }

      ctx.globalCompositeOperation = 'source-over'

      const planetRadius = viewportWidth < 768 ? 18 : 24
      const glow = ctx.createRadialGradient(centerX, centerY, 0, centerX, centerY, planetRadius * 10)
      glow.addColorStop(0, 'rgba(255, 240, 200, 0.55)')
      glow.addColorStop(0.08, 'rgba(255, 212, 59, 0.45)')
      glow.addColorStop(0.2, 'rgba(245, 197, 24, 0.32)')
      glow.addColorStop(0.34, 'rgba(48, 105, 152, 0.24)')
      glow.addColorStop(0.5, 'rgba(38, 84, 121, 0.14)')
      glow.addColorStop(0.7, 'rgba(48, 105, 152, 0.06)')
      glow.addColorStop(1, 'rgba(48, 105, 152, 0)')
      ctx.fillStyle = glow
      ctx.beginPath()
      ctx.arc(centerX, centerY, planetRadius * 10, 0, Math.PI * 2)
      ctx.fill()

      const planet = ctx.createRadialGradient(
        centerX - planetRadius * 0.35, centerY - planetRadius * 0.35, 5,
        centerX, centerY, planetRadius,
      )
      planet.addColorStop(0, '#a3cae0')
      planet.addColorStop(0.3, '#5a8db8')
      planet.addColorStop(0.7, '#306998')
      planet.addColorStop(1, '#152c41')
      ctx.fillStyle = planet
      ctx.beginPath()
      ctx.arc(centerX, centerY, planetRadius, 0, Math.PI * 2)
      ctx.fill()

      ctx.beginPath()
      ctx.arc(centerX - planetRadius * 0.3, centerY - planetRadius * 0.3, 3.2, 0, Math.PI * 2)
      ctx.fillStyle = 'rgba(255, 240, 200, 0.7)'
      ctx.fill()
    }

    function animate(timestamp: number) {
      animId = requestAnimationFrame(animate)
      if (timestamp - lastFrameTime < frameInterval) return
      lastFrameTime = timestamp
      drawFrame()
    }

    resize()
    window.addEventListener('resize', resize)
    startTimer = window.setTimeout(() => {
      drawFrame()
      animId = requestAnimationFrame(animate)
    }, startDelay)

    return () => {
      window.clearTimeout(startTimer)
      cancelAnimationFrame(animId)
      window.removeEventListener('resize', resize)
    }
  }, [])

  const switchTab = useCallback((tab: 'login' | 'register') => {
    setActiveTab(tab)
    setLoginError('')
    setRegError('')
    setShowPassword(false)
  }, [])

  const handleLogin = useCallback(async (e: React.FormEvent) => {
    e.preventDefault()
    setLoginError('')
    setLoading(true)
    try {
      const result = await authStore.login(loginUsername, loginPassword)
      if (result.success) {
        chatStore.loadConversations()
      } else {
        setLoginError(result.message || '登录失败')
      }
    } catch {
      setLoginError('网络错误，请重试')
    } finally {
      setLoading(false)
    }
  }, [loginUsername, loginPassword, authStore, chatStore])

  const handleRegister = useCallback(async (e: React.FormEvent) => {
    e.preventDefault()
    setRegError('')
    if (regUsername.length < 2) {
      setRegError('用户名至少2个字符')
      return
    }
    if (regPassword.length < 4) {
      setRegError('密码至少4个字符')
      return
    }
    setLoading(true)
    try {
      const result = await authStore.register(regUsername, regPassword)
      if (result.success) {
        chatStore.loadConversations()
      } else {
        setRegError(result.message || '注册失败')
      }
    } catch {
      setRegError('网络错误，请重试')
    } finally {
      setLoading(false)
    }
  }, [regUsername, regPassword, authStore, chatStore])

  return (
    <div className="auth-overlay">
      <canvas ref={canvasRef} className="auth-galaxy-canvas" />

      {/* Main card */}
      <div className="auth-card">
        {/* Brand header */}
        <div className="auth-brand">
          <div className="auth-brand-icon" aria-hidden="true">
            &gt;&gt;&gt;
          </div>
          <h1 className="auth-brand-title">Python 智能学习助手</h1>
          <p className="auth-brand-sub">
            <Sparkles className="w-3.5 h-3.5 inline mr-1 -mt-0.5" />
            AI 驱动的个性化学习体验
          </p>
        </div>

        {/* Tab toggle */}
        <div className="auth-tabs">
          <button
            onClick={() => switchTab('login')}
            className={`auth-tab ${activeTab === 'login' ? 'auth-tab-active' : ''}`}
          >
            登录
          </button>
          <button
            onClick={() => switchTab('register')}
            className={`auth-tab ${activeTab === 'register' ? 'auth-tab-active' : ''}`}
          >
            注册
          </button>
          <div className={`auth-tab-indicator ${activeTab === 'register' ? 'auth-tab-indicator-right' : ''}`} />
        </div>

        {/* Forms */}
        <div className="auth-form-area">
          {activeTab === 'login' ? (
            <form key="login" onSubmit={handleLogin} className="auth-form">
              <div className="auth-input-group">
                <User className="auth-input-icon" />
                <input
                  value={loginUsername}
                  onChange={e => setLoginUsername(e.target.value)}
                  type="text"
                  required
                  placeholder="请输入用户名"
                  className="auth-input"
                  autoComplete="username"
                />
              </div>
              <div className="auth-input-group">
                <Lock className="auth-input-icon" />
                <input
                  value={loginPassword}
                  onChange={e => setLoginPassword(e.target.value)}
                  type={showPassword ? 'text' : 'password'}
                  required
                  placeholder="请输入密码"
                  className="auth-input"
                  autoComplete="current-password"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="auth-eye-btn"
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              {loginError && (
                <div className="auth-error">
                  <span>{loginError}</span>
                </div>
              )}
              <button type="submit" disabled={loading} className="auth-submit">
                {loading ? (
                  <span className="auth-loading">
                    <span className="auth-spinner" />
                    登录中...
                  </span>
                ) : '登录'}
              </button>
            </form>
          ) : (
            <form key="register" onSubmit={handleRegister} className="auth-form">
              <div className="auth-input-group">
                <User className="auth-input-icon" />
                <input
                  value={regUsername}
                  onChange={e => setRegUsername(e.target.value)}
                  type="text"
                  required
                  placeholder="用户名（2-50个字符）"
                  className="auth-input"
                  autoComplete="username"
                />
              </div>
              <div className="auth-input-group">
                <Lock className="auth-input-icon" />
                <input
                  value={regPassword}
                  onChange={e => setRegPassword(e.target.value)}
                  type={showPassword ? 'text' : 'password'}
                  required
                  placeholder="密码（至少4个字符）"
                  className="auth-input"
                  autoComplete="new-password"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="auth-eye-btn"
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
              {regError && (
                <div className="auth-error">
                  <span>{regError}</span>
                </div>
              )}
              <button type="submit" disabled={loading} className="auth-submit">
                {loading ? (
                  <span className="auth-loading">
                    <span className="auth-spinner" />
                    注册中...
                  </span>
                ) : '注册并登录'}
              </button>
            </form>
          )}
        </div>

        {/* Footer */}
        <div className="auth-footer">
          <span>让 AI 成为你的编程导师</span>
        </div>
      </div>
    </div>
  )
}

export default AuthModal
