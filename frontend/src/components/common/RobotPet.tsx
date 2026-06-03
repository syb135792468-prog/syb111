import React, { useState, useRef, useEffect, useCallback, useImperativeHandle, forwardRef } from 'react'
import { createPortal } from 'react-dom'

// --- 类型定义 ---
type EyeStyle = 'normal' | 'happy' | 'surprised' | 'thinking' | 'closed' | 'half' | 'dizzy' | 'wink' | 'silly'
type MouthStyle = 'smile' | 'open' | 'o' | 'tongue' | 'frown' | 'none'
type LampColor = 'yellow' | 'blue' | 'pink' | 'green' | 'red' | 'amber' | 'dim'

interface RobotState {
  eyeStyle: EyeStyle
  mouthStyle: MouthStyle
  lampColor: LampColor
  lampBlink: boolean
  pupilX: number
  pupilY: number
  armAngleL: number
  armAngleR: number
  legAngleL: number
  legAngleR: number
  antennaWobble: number
  jumping: boolean
  rotating: boolean
  shaking: boolean
  thinking: boolean
  sleeping: boolean
  welcoming: boolean
  yawn: boolean
  showHi: boolean
  showZzz: boolean
  buttonFlash: boolean
  idleBlink: boolean
}

interface Position {
  x: number
  y: number
}

export interface RobotPetHandle {
  triggerThink: () => void
}

// --- 常量 ---
const MESSAGES = [
  '加油！你学得很快！', '这个知识点掌握得不错！', '坚持下去，你会成为编程大神的！',
  '遇到困难了吗？别放弃！', '写代码的你真帅！', '今天又进步了一点点！',
  'Python其实很简单，对吧？', '你已经很棒了！', '再坚持一下，马上就学会了！',
  '编程是最酷的技能！', '错误是最好的老师！', '你正在变得越来越强！',
  '今天的学习任务完成得很好！', '休息一下，然后继续前进！', '你对Python的理解越来越深了！',
  '太棒了！又学会了一个新技能！', '不要怕犯错，每个人都是这么过来的！',
  '你正在创造奇迹！', '学习编程是最正确的选择！', '我相信你一定可以的！',
  '专注是成功的关键！', '每行代码都是进步！',
]

const INITIAL_STATE: RobotState = {
  eyeStyle: 'normal', mouthStyle: 'smile', lampColor: 'yellow', lampBlink: false,
  pupilX: 0, pupilY: 0, armAngleL: 0, armAngleR: 0, legAngleL: 0, legAngleR: 0,
  antennaWobble: 0, jumping: false, rotating: false, shaking: false, thinking: false,
  sleeping: false, welcoming: false, yawn: false, showHi: false, showZzz: false,
  buttonFlash: false, idleBlink: false,
}

// --- 工具函数 ---
function ri(min: number, max: number) { return Math.floor(Math.random() * (max - min + 1)) + min }
function rmsg() { return MESSAGES[ri(0, MESSAGES.length - 1)] }

function getLampBg(c: LampColor): string {
  switch (c) {
    case 'amber': return '#F59E0B'
    case 'pink': return '#ec4899'
    case 'green': return '#10b981'
    case 'red': return '#ef4444'
    case 'blue': return '#4A90E2'
    case 'dim': return '#d1d5db'
    default: return '#FFD166'
  }
}

// --- 组件 ---
const RobotPet = forwardRef<RobotPetHandle>((_props, ref) => {
  const [visible, setVisible] = useState(true)
  const [pos, setPos] = useState<Position>({ x: 0, y: 0 })
  const [dragging, setDragging] = useState(false)
  const [isMobile, setIsMobile] = useState(false)
  const [scaleVal, setScaleVal] = useState(1)
  const [state, setState] = useState<RobotState>(INITIAL_STATE)
  const [bubble, setBubble] = useState({ text: '', show: false })
  const [contextMenu, setContextMenu] = useState({ show: false, x: 0, y: 0 })

  const robotRef = useRef<HTMLDivElement>(null)
  const dragOffset = useRef<Position>({ x: 0, y: 0 })
  const idleTime = useRef(0)
  const animTimers = useRef<Array<ReturnType<typeof setTimeout>>>([])

  // Timer refs
  const pupilTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const lampTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const idleTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const bubbleTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const thinkTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const armTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const legTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const antennaTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const blinkTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const lampInnerTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const antennaInnerTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const blinkInnerTimer = useRef<ReturnType<typeof setTimeout> | null>(null)

  // --- 位置管理 ---
  const getPetSize = useCallback(() => {
    const w = window.innerWidth
    return w < 768 ? 36 : 44
  }, [])

  const resetPos = useCallback(() => {
    const sz = getPetSize()
    setPos({ x: window.innerWidth - sz - 24, y: window.innerHeight - sz - 24 })
  }, [getPetSize])

  const savePos = useCallback((p: Position) => {
    localStorage.setItem('robot-pet-pos', JSON.stringify(p))
  }, [])

  const loadPos = useCallback(() => {
    const s = localStorage.getItem('robot-pet-pos')
    if (s) {
      const p = JSON.parse(s)
      setPos({ x: p.x, y: p.y })
    } else {
      resetPos()
    }
  }, [resetPos])

  // --- 气泡 ---
  const showBubble = useCallback((t?: string) => {
    if (bubbleTimer.current) clearTimeout(bubbleTimer.current)
    const text = t || rmsg()
    setBubble({ text, show: true })
    bubbleTimer.current = setTimeout(() => setBubble({ text: '', show: false }), 3000)
  }, [])

  // --- 重置空闲 ---
  const resetIdle = useCallback(() => {
    idleTime.current = 0
    setState(prev => {
      if (!prev.sleeping) return prev
      return { ...prev, sleeping: false, yawn: false, showZzz: false, eyeStyle: 'normal', mouthStyle: 'smile', lampColor: 'yellow' }
    })
  }, [])

  // --- 动作 ---
  const doSleep = useCallback(() => {
    setState(prev => ({ ...prev, sleeping: true, yawn: true, eyeStyle: 'closed', mouthStyle: 'o', lampColor: 'dim' }))
    const t = setTimeout(() => {
      setState(prev => ({ ...prev, yawn: false, showZzz: true, eyeStyle: 'half', mouthStyle: 'none' }))
    }, 1500)
    animTimers.current.push(t)
  }, [])

  const doWelcome = useCallback(() => {
    setState(prev => ({ ...prev, welcoming: true, showHi: true, eyeStyle: 'happy', mouthStyle: 'open', lampColor: 'blue', lampBlink: true }))
    let count = 0
    const iv = setInterval(() => {
      setState(prev => ({ ...prev, armAngleR: count % 2 === 0 ? -25 : 12 }))
      count++
      if (count > 10) { clearInterval(iv); setState(prev => ({ ...prev, armAngleR: 0 })) }
    }, 120)
    animTimers.current.push(iv)
    const t = setTimeout(() => {
      setState(prev => ({ ...prev, welcoming: false, showHi: false, eyeStyle: 'normal', mouthStyle: 'smile', lampBlink: false, lampColor: 'yellow' }))
    }, 1500)
    animTimers.current.push(t)
  }, [])

  // --- 触发思考（外部调用） ---
  const triggerThink = useCallback(() => {
    if (thinkTimer.current) clearTimeout(thinkTimer.current)
    setState(prev => ({
      ...prev, thinking: true, lampColor: 'amber', lampBlink: true,
      eyeStyle: 'thinking', mouthStyle: 'frown', pupilX: 0, pupilY: 0,
      armAngleL: 4, armAngleR: -4,
    }))
    let spin = 0
    const iv = setInterval(() => {
      setState(prev => ({ ...prev, antennaWobble: (spin % 8) * 45 - 180 }))
      spin++
    }, 80)
    animTimers.current.push(iv)
    thinkTimer.current = setTimeout(() => {
      clearInterval(iv)
      setState(prev => ({
        ...prev, thinking: false, lampBlink: false, lampColor: 'yellow',
        eyeStyle: 'normal', mouthStyle: 'smile', armAngleL: 0, armAngleR: 0, antennaWobble: 0,
      }))
    }, 3000)
  }, [])

  useImperativeHandle(ref, () => ({ triggerThink }), [triggerThink])

  // --- 点击头部 ---
  const onHeadClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    resetIdle()
    setState(prev => ({ ...prev, jumping: true, eyeStyle: 'happy', mouthStyle: 'open', lampColor: 'blue', lampBlink: true }))
    showBubble()
    let count = 0
    const iv = setInterval(() => {
      setState(prev => ({
        ...prev,
        armAngleL: count % 2 === 0 ? -20 : 12,
        armAngleR: count % 2 === 0 ? 12 : -20,
        legAngleL: count % 2 === 0 ? -6 : 3,
        legAngleR: count % 2 === 0 ? 3 : -6,
      }))
      count++
      if (count > 8) {
        clearInterval(iv)
        setState(prev => ({ ...prev, armAngleL: 0, armAngleR: 0, legAngleL: 0, legAngleR: 0 }))
      }
    }, 120)
    animTimers.current.push(iv)
    const t = setTimeout(() => {
      setState(prev => ({ ...prev, jumping: false, lampBlink: false, eyeStyle: 'normal', mouthStyle: 'smile', lampColor: 'yellow' }))
    }, 1200)
    animTimers.current.push(t)
  }, [resetIdle, showBubble])

  // --- 点击身体 ---
  const onBodyClick = useCallback((e: React.MouseEvent) => {
    e.stopPropagation()
    resetIdle()
    setState(prev => ({ ...prev, shaking: true, buttonFlash: true, eyeStyle: 'wink', mouthStyle: 'tongue', lampColor: 'pink' }))
    const t = setTimeout(() => {
      setState(prev => ({ ...prev, shaking: false, buttonFlash: false, eyeStyle: 'normal', mouthStyle: 'smile', lampColor: 'yellow' }))
    }, 800)
    animTimers.current.push(t)
  }, [resetIdle])

  // --- 双击 ---
  const onDblClick = useCallback(() => {
    resetIdle()
    setState(prev => ({
      ...prev, rotating: true, eyeStyle: 'dizzy', mouthStyle: 'o',
      lampColor: 'blue', lampBlink: true, armAngleL: -35, armAngleR: -35,
    }))
    let count = 0
    const iv = setInterval(() => {
      setState(prev => ({
        ...prev,
        armAngleL: count % 2 === 0 ? -35 : -15,
        armAngleR: count % 2 === 0 ? -35 : -15,
      }))
      count++
    }, 80)
    animTimers.current.push(iv)
    const t = setTimeout(() => {
      clearInterval(iv)
      setState(prev => ({
        ...prev, rotating: false, eyeStyle: 'normal', mouthStyle: 'smile',
        lampBlink: false, lampColor: 'yellow', armAngleL: 0, armAngleR: 0,
      }))
    }, 900)
    animTimers.current.push(t)
  }, [resetIdle])

  // --- 拖拽 ---
  const onDragMove = useCallback((e: MouseEvent | TouchEvent) => {
    const cx = 'touches' in e ? e.touches[0].clientX : e.clientX
    const cy = 'touches' in e ? e.touches[0].clientY : e.clientY
    const sz = window.innerWidth < 768 ? 36 : 44
    setPos({
      x: Math.max(0, Math.min(window.innerWidth - sz, cx - dragOffset.current.x - sz / 2)),
      y: Math.max(0, Math.min(window.innerHeight - sz, cy - dragOffset.current.y - sz / 2)),
    })
  }, [])

  const onDragEnd = useCallback(() => {
    setDragging(false)
    setState(prev => ({
      ...prev, lampBlink: false, eyeStyle: 'half', mouthStyle: 'smile',
      lampColor: 'green', armAngleL: 0, armAngleR: 0, legAngleL: 0, legAngleR: 0,
    }))
    setScaleVal(1.05)
    setTimeout(() => setScaleVal(0.98), 100)
    setTimeout(() => {
      setScaleVal(1)
      setState(prev => ({ ...prev, lampColor: 'yellow', eyeStyle: 'normal' }))
    }, 300)
    document.removeEventListener('mousemove', onDragMove)
    document.removeEventListener('mouseup', onDragEnd)
    document.removeEventListener('touchmove', onDragMove)
    document.removeEventListener('touchend', onDragEnd)
  }, [onDragMove])

  const onDragStart = useCallback((e: React.MouseEvent | React.TouchEvent) => {
    e.preventDefault()
    resetIdle()
    setContextMenu({ show: false, x: 0, y: 0 })
    let cx: number, cy: number
    if ('touches' in e) {
      cx = e.touches[0].clientX
      cy = e.touches[0].clientY
    } else {
      cx = e.clientX
      cy = e.clientY
    }
    const sz = window.innerWidth < 768 ? 36 : 44
    dragOffset.current = { x: cx - pos.x - sz / 2, y: cy - pos.y - sz / 2 }
    setDragging(true)
    setScaleVal(0.95)
    setState(prev => ({
      ...prev, eyeStyle: 'surprised', mouthStyle: 'o', lampColor: 'red', lampBlink: true,
      armAngleL: -8, armAngleR: -8, legAngleL: 4, legAngleR: 4,
    }))
    document.addEventListener('mousemove', onDragMove, { passive: false })
    document.addEventListener('mouseup', onDragEnd)
    document.addEventListener('touchmove', onDragMove, { passive: false })
    document.addEventListener('touchend', onDragEnd)
  }, [pos, resetIdle, onDragMove, onDragEnd])

  // --- 右键菜单 ---
  const onContextMenuHandler = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    resetIdle()
    setContextMenu({ show: true, x: e.clientX, y: e.clientY })
  }, [resetIdle])

  const hidePet = useCallback(() => {
    setVisible(false)
    setContextMenu({ show: false, x: 0, y: 0 })
    localStorage.setItem('robot-pet-hidden', 'true')
  }, [])

  const showPetHandler = useCallback(() => {
    setVisible(true)
    localStorage.setItem('robot-pet-hidden', 'false')
    resetPos()
    const t = setTimeout(doWelcome, 500)
    animTimers.current.push(t)
  }, [resetPos, doWelcome])

  const handleResetPos = useCallback(() => {
    const sz = window.innerWidth < 768 ? 36 : 44
    const newPos = { x: window.innerWidth - sz - 24, y: window.innerHeight - sz - 24 }
    setPos(newPos)
    savePos(newPos)
    setContextMenu({ show: false, x: 0, y: 0 })
  }, [savePos])

  // --- 初始化 + 定时器 ---
  useEffect(() => {
    const mobile = window.innerWidth < 768
    setIsMobile(mobile)
    const hidden = localStorage.getItem('robot-pet-hidden') === 'true'
    setVisible(!hidden)
    loadPos()

    // 定时器
    pupilTimer.current = setInterval(() => {
      setState(prev => {
        if (prev.sleeping || prev.thinking) return prev
        return { ...prev, pupilX: ri(-1, 1), pupilY: ri(-1, 1) }
      })
    }, 3000)

    lampTimer.current = setInterval(() => {
      setState(prev => {
        if (prev.thinking || prev.sleeping) return prev
        if (lampInnerTimer.current) clearTimeout(lampInnerTimer.current)
        lampInnerTimer.current = setTimeout(() => setState(p => ({ ...p, lampBlink: false })), 200)
        return { ...prev, lampBlink: true }
      })
    }, ri(5000, 7000))

    armTimer.current = setInterval(() => {
      setState(prev => {
        if (prev.thinking || prev.sleeping || prev.rotating || prev.jumping) return prev
        const a = ri(-2, 2)
        return { ...prev, armAngleL: a, armAngleR: -a }
      })
    }, 2500)

    legTimer.current = setInterval(() => {
      setState(prev => {
        if (prev.thinking || prev.sleeping || prev.rotating || prev.jumping) return prev
        return { ...prev, legAngleL: ri(-1, 1), legAngleR: ri(-1, 1) }
      })
    }, 3000)

    antennaTimer.current = setInterval(() => {
      setState(prev => {
        if (prev.sleeping) return prev
        if (antennaInnerTimer.current) clearTimeout(antennaInnerTimer.current)
        antennaInnerTimer.current = setTimeout(() => setState(p => ({ ...p, antennaWobble: 0 })), 400)
        return { ...prev, antennaWobble: ri(-3, 3) }
      })
    }, 2000)

    blinkTimer.current = setInterval(() => {
      setState(prev => {
        if (prev.sleeping || prev.thinking || prev.eyeStyle !== 'normal') return prev
        if (blinkInnerTimer.current) clearTimeout(blinkInnerTimer.current)
        blinkInnerTimer.current = setTimeout(() => setState(p => ({ ...p, idleBlink: false })), 150)
        return { ...prev, idleBlink: true }
      })
    }, ri(3000, 6000))

    idleTimer.current = setInterval(() => {
      idleTime.current += 10000
      if (idleTime.current >= 300000) doSleep()
    }, 10000)

    // 事件监听
    const closeCtx = () => setContextMenu({ show: false, x: 0, y: 0 })
    const onKeydown = (e: KeyboardEvent) => { if (e.key === 'Escape') setContextMenu({ show: false, x: 0, y: 0 }) }
    const onResize = () => setIsMobile(window.innerWidth < 768)

    document.addEventListener('click', closeCtx)
    document.addEventListener('keydown', onKeydown)
    window.addEventListener('resize', onResize)
    window.addEventListener('robot-think', triggerThink)

    if (!hidden) {
      const t = setTimeout(doWelcome, 500)
      animTimers.current.push(t)
    }

    return () => {
      if (pupilTimer.current) clearInterval(pupilTimer.current)
      if (lampTimer.current) clearInterval(lampTimer.current)
      if (idleTimer.current) clearInterval(idleTimer.current)
      if (armTimer.current) clearInterval(armTimer.current)
      if (legTimer.current) clearInterval(legTimer.current)
      if (antennaTimer.current) clearInterval(antennaTimer.current)
      if (blinkTimer.current) clearInterval(blinkTimer.current)
      if (lampInnerTimer.current) clearTimeout(lampInnerTimer.current)
      if (antennaInnerTimer.current) clearTimeout(antennaInnerTimer.current)
      if (blinkInnerTimer.current) clearTimeout(blinkInnerTimer.current)
      if (bubbleTimer.current) clearTimeout(bubbleTimer.current)
      if (thinkTimer.current) clearTimeout(thinkTimer.current)
      // Clean up all user-triggered animation timers
      animTimers.current.forEach(t => { clearTimeout(t); clearInterval(t) })
      animTimers.current = []
      document.removeEventListener('click', closeCtx)
      document.removeEventListener('keydown', onKeydown)
      window.removeEventListener('resize', onResize)
      window.removeEventListener('robot-think', triggerThink)
      document.removeEventListener('mousemove', onDragMove)
      document.removeEventListener('mouseup', onDragEnd)
      document.removeEventListener('touchmove', onDragMove)
      document.removeEventListener('touchend', onDragEnd)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const petSize = isMobile ? 36 : 44

  return (
    <>
      {/* Hidden icon */}
      {!visible && (
        <div
          onClick={showPetHandler}
          title="显示宠物"
          style={{
            position: 'fixed', bottom: 24, right: 24, zIndex: 9999,
            width: 16, height: 16, background: '#FF6B6B', cursor: 'pointer',
            opacity: 0.4, transition: 'opacity 0.15s',
          }}
          onMouseEnter={e => (e.currentTarget.style.opacity = '0.8')}
          onMouseLeave={e => (e.currentTarget.style.opacity = '0.4')}
        />
      )}

      {/* Robot */}
      {visible && (
        <div
          ref={robotRef}
          style={{
            position: 'fixed', left: pos.x, top: pos.y, zIndex: 9999,
            cursor: dragging ? 'grabbing' : 'grab', userSelect: 'none',
            transition: dragging ? 'none' : 'transform 0.15s cubic-bezier(0.4,0,0.2,1)',
            transform: `scale(${scaleVal})`, transformOrigin: 'center bottom',
            imageRendering: 'pixelated',
          }}
          onMouseDown={onDragStart}
          onTouchStart={onDragStart}
          onContextMenu={onContextMenuHandler}
          onDoubleClick={onDblClick}
          onMouseMove={resetIdle}
        >
          {/* Bubble */}
          {bubble.show && (
            <div style={{
              position: 'absolute', bottom: '100%', left: '50%', transform: 'translateX(-50%)',
              marginBottom: 10, background: '#fff', border: '2px solid #E53E3E',
              padding: '6px 10px', fontSize: 11, color: '#374151', whiteSpace: 'nowrap',
              boxShadow: '2px 2px 0 #E53E3E', pointerEvents: 'none', lineHeight: 1.4,
            }}>
              {bubble.text}
            </div>
          )}

          {/* Hi text */}
          {state.showHi && (
            <div style={{
              position: 'absolute', top: -4, right: -8, fontSize: 9, fontWeight: 700,
              color: '#FF6B6B', animation: 'floatUp 1.2s ease-in-out', pointerEvents: 'none',
            }}>Hi!</div>
          )}

          {/* Zzz text */}
          {state.showZzz && (
            <div style={{
              position: 'absolute', top: -4, right: -2, fontSize: 8, color: '#9ca3af',
              fontWeight: 600, animation: 'floatUp 2s ease-in-out infinite', pointerEvents: 'none',
            }}>z</div>
          )}

          {/* S container */}
          <div style={{
            width: petSize, height: petSize, position: 'relative',
            transform: state.jumping ? 'translateY(-10px)' : '',
            transition: state.jumping ? 'transform 0.2s ease' : '',
            animation: state.rotating ? 'robotRotate 0.9s cubic-bezier(0.4,0,0.2,1)' : 'none',
          }}>
            {/* Antenna */}
            <div style={{
              position: 'absolute', top: isMobile ? -10 : -12, left: isMobile ? 13 : 17,
              display: 'flex', flexDirection: 'column', alignItems: 'center',
              transform: `rotate(${state.antennaWobble}deg)`, transformOrigin: 'bottom center',
              transition: 'transform 0.3s cubic-bezier(0.4,0,0.2,1)',
            }}>
              <div style={{
                width: 4, height: 4, background: getLampBg(state.lampColor),
                border: '1px solid #E53E3E',
                animation: state.lampBlink ? 'lampPulse 0.4s infinite' : 'none',
                transition: 'background 0.2s',
              }} />
              <div style={{ width: 2, height: 6, background: '#9CA3AF' }} />
            </div>

            {/* Left arm */}
            <div style={{
              position: 'absolute', left: isMobile ? -10 : -12, top: isMobile ? 19 : 24,
              display: 'flex', flexDirection: 'column', alignItems: 'center',
              transform: `rotate(${state.armAngleL}deg)`, transformOrigin: 'top center',
              transition: 'transform 0.25s cubic-bezier(0.4,0,0.2,1)',
            }}>
              <div style={{ width: 6, height: 6, background: '#9CA3AF', border: '1px solid #6B7280' }} />
              <div style={{ width: 8, height: 6, background: '#FF6B6B', border: '1px solid #E53E3E' }} />
            </div>

            {/* Right arm */}
            <div style={{
              position: 'absolute', right: isMobile ? -10 : -12, top: isMobile ? 19 : 24,
              display: 'flex', flexDirection: 'column', alignItems: 'center',
              transform: `rotate(${state.armAngleR}deg)`, transformOrigin: 'top center',
              transition: 'transform 0.25s cubic-bezier(0.4,0,0.2,1)',
            }}>
              <div style={{ width: 6, height: 6, background: '#9CA3AF', border: '1px solid #6B7280' }} />
              <div style={{ width: 8, height: 6, background: '#FF6B6B', border: '1px solid #E53E3E' }} />
            </div>

            {/* Left leg */}
            <div style={{
              position: 'absolute', bottom: isMobile ? -12 : -14, left: isMobile ? 6 : 9,
              display: 'flex', flexDirection: 'column', alignItems: 'center',
              transform: `rotate(${state.legAngleL}deg)`, transformOrigin: 'top center',
              transition: 'transform 0.25s cubic-bezier(0.4,0,0.2,1)',
            }}>
              <div style={{ width: 6, height: 8, background: '#9CA3AF', border: '1px solid #6B7280' }} />
              <div style={{ width: 10, height: 6, background: '#FF6B6B', border: '1px solid #E53E3E' }} />
            </div>

            {/* Right leg */}
            <div style={{
              position: 'absolute', bottom: isMobile ? -12 : -14, right: isMobile ? 6 : 9,
              display: 'flex', flexDirection: 'column', alignItems: 'center',
              transform: `rotate(${state.legAngleR}deg)`, transformOrigin: 'top center',
              transition: 'transform 0.25s cubic-bezier(0.4,0,0.2,1)',
            }}>
              <div style={{ width: 6, height: 8, background: '#9CA3AF', border: '1px solid #6B7280' }} />
              <div style={{ width: 10, height: 6, background: '#FF6B6B', border: '1px solid #E53E3E' }} />
            </div>

            {/* Body */}
            <div onClick={onBodyClick} style={{
              position: 'absolute', top: isMobile ? 17 : 21, left: '50%', transform: 'translateX(-50%)',
              width: isMobile ? 20 : 24, height: isMobile ? 16 : 20,
              background: '#FF6B6B', cursor: 'pointer', border: '2px solid #E53E3E',
              animation: 'breathe 3s ease-in-out infinite',
            }}>
              <div style={{
                position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%,-50%)',
                width: 4, height: 4, background: '#FFD166', border: '1px solid #E53E3E',
                animation: state.buttonFlash ? 'lampPulse 0.3s infinite' : 'none',
              }} />
            </div>

            {/* Head */}
            <div onClick={onHeadClick} style={{
              position: 'absolute', top: isMobile ? 2 : 3, left: '50%', transform: 'translateX(-50%)',
              width: isMobile ? 22 : 26, height: isMobile ? 18 : 22,
              background: '#FF6B6B', cursor: 'pointer', border: '2px solid #E53E3E',
            }}>
              {/* Face screen */}
              <div style={{
                position: 'absolute', top: 3, left: '50%', transform: 'translateX(-50%)',
                width: isMobile ? 16 : 20, height: isMobile ? 12 : 14,
                background: '#ffffff', border: '2px solid #E53E3E', overflow: 'hidden',
              }}>
                {/* Normal eyes + smile */}
                {state.eyeStyle === 'normal' && (
                  <>
                    <div style={{
                      position: 'absolute', top: 1, left: 1,
                      width: isMobile ? 5 : 6, height: isMobile ? 5 : 6, background: '#4A90E2',
                      transition: 'transform 0.4s cubic-bezier(0.4,0,0.2,1)',
                      transform: `translate(${state.pupilX}px,${state.pupilY}px)`,
                    }}>
                      <div style={{ position: 'absolute', top: 1, left: 1, width: 2, height: 2, background: '#fff' }} />
                    </div>
                    <div style={{
                      position: 'absolute', top: 1, right: 1,
                      width: isMobile ? 5 : 6, height: isMobile ? 5 : 6, background: '#4A90E2',
                      transition: 'transform 0.4s cubic-bezier(0.4,0,0.2,1)',
                      transform: `translate(${-state.pupilX}px,${state.pupilY}px)`,
                    }}>
                      <div style={{ position: 'absolute', top: 1, left: 1, width: 2, height: 2, background: '#fff' }} />
                    </div>
                    {state.idleBlink && <div style={{ position: 'absolute', top: 1, left: 0, right: 0, height: 6, background: '#fff', zIndex: 1 }} />}
                    {state.mouthStyle === 'smile' && <div style={{ position: 'absolute', bottom: 1, left: '50%', transform: 'translateX(-50%)', width: 4, height: 2, borderBottom: '2px solid #E53E3E' }} />}
                  </>
                )}
                {/* Happy ^_^ */}
                {state.eyeStyle === 'happy' && (
                  <>
                    <div style={{ position: 'absolute', top: 2, left: 1, width: 5, height: 2, borderTop: '2px solid #4A90E2' }} />
                    <div style={{ position: 'absolute', top: 2, right: 1, width: 5, height: 2, borderTop: '2px solid #4A90E2' }} />
                    {state.mouthStyle === 'open' && <div style={{ position: 'absolute', bottom: 1, left: '50%', transform: 'translateX(-50%)', width: 6, height: 3, background: '#E53E3E' }} />}
                  </>
                )}
                {/* Surprised O_O */}
                {state.eyeStyle === 'surprised' && (
                  <>
                    <div style={{ position: 'absolute', top: 0, left: 1, width: 6, height: 6, background: '#4A90E2', border: '2px solid #1a1a2e' }}>
                      <div style={{ position: 'absolute', top: 1, left: 1, width: 2, height: 2, background: '#fff' }} />
                    </div>
                    <div style={{ position: 'absolute', top: 0, right: 1, width: 6, height: 6, background: '#4A90E2', border: '2px solid #1a1a2e' }}>
                      <div style={{ position: 'absolute', top: 1, left: 1, width: 2, height: 2, background: '#fff' }} />
                    </div>
                    {state.mouthStyle === 'o' && <div style={{ position: 'absolute', bottom: 1, left: '50%', transform: 'translateX(-50%)', width: 4, height: 4, background: '#E53E3E' }} />}
                  </>
                )}
                {/* Wink o_O */}
                {state.eyeStyle === 'wink' && (
                  <>
                    <div style={{ position: 'absolute', top: 3, left: 1, width: 5, height: 2, background: '#4A90E2' }} />
                    <div style={{ position: 'absolute', top: 1, right: 1, width: 5, height: 5, background: '#4A90E2' }}>
                      <div style={{ position: 'absolute', top: 1, left: 1, width: 2, height: 2, background: '#fff' }} />
                    </div>
                    {state.mouthStyle === 'tongue' && <div style={{ position: 'absolute', bottom: 0, left: '50%', transform: 'translateX(-50%)', width: 4, height: 3, background: '#ec4899' }} />}
                  </>
                )}
                {/* Thinking */}
                {state.eyeStyle === 'thinking' && (
                  <>
                    <div style={{ position: 'absolute', top: 1, left: 1, width: 5, height: 5, background: '#4A90E2' }}>
                      <div style={{ position: 'absolute', top: 0, left: 2, width: 2, height: 2, background: '#fff' }} />
                    </div>
                    <div style={{ position: 'absolute', top: 1, right: 1, width: 5, height: 5, background: '#4A90E2' }}>
                      <div style={{ position: 'absolute', top: 0, left: 2, width: 2, height: 2, background: '#fff' }} />
                    </div>
                    {state.mouthStyle === 'frown' && <div style={{ position: 'absolute', bottom: 1, left: '50%', transform: 'translateX(-50%)', width: 4, height: 2, borderTop: '2px solid #E53E3E' }} />}
                  </>
                )}
                {/* Closed */}
                {state.eyeStyle === 'closed' && (
                  <>
                    <div style={{ position: 'absolute', top: 3, left: 1, width: 5, height: 2, background: '#4A90E2' }} />
                    <div style={{ position: 'absolute', top: 3, right: 1, width: 5, height: 2, background: '#4A90E2' }} />
                  </>
                )}
                {/* Half */}
                {state.eyeStyle === 'half' && (
                  <>
                    <div style={{ position: 'absolute', top: 2, left: 1, width: 5, height: 3, background: '#4A90E2' }} />
                    <div style={{ position: 'absolute', top: 2, right: 1, width: 5, height: 3, background: '#4A90E2' }} />
                  </>
                )}
                {/* Dizzy @_@ */}
                {state.eyeStyle === 'dizzy' && (
                  <>
                    <div style={{ position: 'absolute', top: 1, left: 0, width: 6, height: 6, border: '2px solid #4A90E2', borderTopColor: 'transparent', animation: 'eyeSpin 0.4s linear infinite' }} />
                    <div style={{ position: 'absolute', top: 1, right: 0, width: 6, height: 6, border: '2px solid #4A90E2', borderTopColor: 'transparent', animation: 'eyeSpin 0.4s linear infinite reverse' }} />
                    {state.mouthStyle === 'o' && <div style={{ position: 'absolute', bottom: 1, left: '50%', transform: 'translateX(-50%)', width: 4, height: 4, background: '#E53E3E' }} />}
                  </>
                )}
                {/* Silly */}
                {state.eyeStyle === 'silly' && (
                  <>
                    <div style={{ position: 'absolute', top: 1, left: 1, width: 5, height: 5, background: '#4A90E2' }}>
                      <div style={{ position: 'absolute', top: 1, left: 1, width: 2, height: 2, background: '#fff' }} />
                    </div>
                    <div style={{ position: 'absolute', top: 3, right: 1, width: 5, height: 2, background: '#4A90E2' }} />
                    <div style={{ position: 'absolute', bottom: 0, left: '50%', transform: 'translateX(-50%)', width: 5, height: 3, background: '#ec4899' }} />
                  </>
                )}
              </div>
            </div>

            {/* Shaking animation */}
            {state.shaking && <div style={{ position: 'absolute', inset: 0, animation: 'shake 0.4s ease-in-out' }} />}
          </div>
        </div>
      )}

      {/* Context Menu */}
      {contextMenu.show && createPortal(
        <div
          style={{
            position: 'fixed', left: contextMenu.x, top: contextMenu.y, zIndex: 10000,
            background: '#fff', border: '2px solid #E53E3E', padding: 4,
            boxShadow: '2px 2px 0 #E53E3E', minWidth: 120,
          }}
          onClick={e => e.stopPropagation()}
        >
          <button
            onClick={hidePet}
            style={{ width: '100%', padding: '6px 10px', background: 'transparent', border: 'none', fontSize: 12, color: '#374151', cursor: 'pointer', textAlign: 'left', transition: 'background 0.15s' }}
            onMouseEnter={e => (e.currentTarget.style.background = '#f3f4f6')}
            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
          >隐藏宠物</button>
          <button
            onClick={handleResetPos}
            style={{ width: '100%', padding: '6px 10px', background: 'transparent', border: 'none', fontSize: 12, color: '#374151', cursor: 'pointer', textAlign: 'left', transition: 'background 0.15s' }}
            onMouseEnter={e => (e.currentTarget.style.background = '#f3f4f6')}
            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
          >重置位置</button>
        </div>,
        document.body
      )}

      {/* Animations */}
      <style>{`
        @keyframes breathe {
          0%,100% { transform: translateX(-50%) scale(1); }
          50% { transform: translateX(-50%) scale(1.02); }
        }
        @keyframes robotRotate { to { transform: rotate(360deg); } }
        @keyframes lampPulse { 0%,49% { opacity: 1; } 50%,100% { opacity: 0.3; } }
        @keyframes floatUp {
          0%,100% { transform: translateY(0); opacity: 0.6; }
          50% { transform: translateY(-3px); opacity: 1; }
        }
        @keyframes eyeSpin { to { transform: rotate(360deg); } }
        @keyframes shake {
          0%,100% { transform: translateX(-50%) rotate(0); }
          20% { transform: translateX(-50%) rotate(-3deg); }
          40% { transform: translateX(-50%) rotate(3deg); }
          60% { transform: translateX(-50%) rotate(-2deg); }
          80% { transform: translateX(-50%) rotate(2deg); }
        }
      `}</style>
    </>
  )
})

RobotPet.displayName = 'RobotPet'

export default RobotPet
