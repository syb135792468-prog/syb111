import React, { useState, useCallback } from 'react'
import { GraduationCap, User, Lock, Eye, EyeOff, Sparkles } from 'lucide-react'

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
      {/* Animated background blobs */}
      <div className="auth-bg">
        <div className="auth-blob auth-blob-1" />
        <div className="auth-blob auth-blob-2" />
        <div className="auth-blob auth-blob-3" />
        <div className="auth-blob auth-blob-4" />
      </div>

      {/* Main card */}
      <div className="auth-card">
        {/* Brand header */}
        <div className="auth-brand">
          <div className="auth-brand-icon">
            <GraduationCap className="w-7 h-7 text-white" />
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
