import React, { useEffect, useRef, useCallback } from 'react'
import 'reveal.js/reveal.css'
import 'reveal.js/plugin/highlight/monokai.css'
import type { SlideStyle } from './slideStyles'

interface SlidesViewerProps {
  content: string
  fullscreen?: boolean
  onClose?: () => void
  style?: SlideStyle
}

const SlidesViewer: React.FC<SlidesViewerProps> = ({ content, fullscreen = false, onClose, style = 'python-blue' }) => {
  const deckRef = useRef<HTMLDivElement>(null)
  const revealRef = useRef<any>(null)

  const initReveal = useCallback(async () => {
    if (!deckRef.current) return

    if (revealRef.current) {
      try { revealRef.current.destroy() } catch {}
      revealRef.current = null
    }

    const Reveal = (await import('reveal.js')).default
    const Markdown = (await import('reveal.js/plugin/markdown')).default
    const Highlight = (await import('reveal.js/plugin/highlight')).default

    // 清理 LLM 返回的代码块包裹
    let cleaned = content.trim()
    if (cleaned.startsWith('```')) {
      cleaned = cleaned.replace(/^```(?:markdown|md)?\s*\n?/i, '').replace(/\n?```\s*$/i, '').trim()
    }

    // 代码块保护
    const codeBlocks: string[] = []
    const protected_content = cleaned.replace(/```[\s\S]*?```/g, (match) => {
      codeBlocks.push(match)
      return `__CODE_BLOCK_${codeBlocks.length - 1}__`
    })

    const slides = protected_content
      .split(/\n\s*---\s*\n/)
      .map(s => s.replace(/__CODE_BLOCK_(\d+)__/g, (_, i) => codeBlocks[parseInt(i)]).trim())
      .filter(Boolean)

    if (slides.length < 2 && cleaned.includes('---')) {
      const fallback = cleaned.split(/---/).filter(s => s.trim())
      if (fallback.length > 1) {
        slides.length = 0
        slides.push(...fallback)
      }
    }

    // 为封面页（第一页）添加特殊 class
    const sections = slides.map((slide, i) => {
      const escaped = slide.replace(/<\/textarea>/gi, '&lt;/textarea&gt;')
      const attrs = i === 0 ? ' class="title-slide"' : ''
      return `<section${attrs} data-markdown><textarea data-template>${escaped}</textarea></section>`
    }).join('')
    deckRef.current.innerHTML = `<div class="slides">${sections}</div>`

    const deck = new Reveal(deckRef.current, {
      plugins: [Markdown, Highlight],
      embedded: true,
      controls: true,
      hash: false,
      slideNumber: 'c/t',
      transition: 'slide',
      transitionSpeed: 'default',
      width: 1280,
      height: 720,
      margin: 0.04,
      minScale: 0.8,
      maxScale: 1.2,
      center: false,
    })

    await deck.initialize()
    deck.layout()
    revealRef.current = deck
  }, [content, fullscreen, style])

  useEffect(() => {
    initReveal()
    return () => {
      if (revealRef.current) {
        try { revealRef.current.destroy() } catch {}
        revealRef.current = null
      }
    }
  }, [initReveal])

  useEffect(() => {
    if (revealRef.current) {
      setTimeout(() => revealRef.current.layout(), 100)
    }
  }, [fullscreen])

  const handleFullscreen = useCallback(async () => {
    if (!document.fullscreenElement && deckRef.current) {
      try { await deckRef.current.requestFullscreen() } catch {}
    }
  }, [])

  const handleExportPDF = useCallback(async () => {
    if (!deckRef.current) return

    // reveal.js 6 标准打印模式：给 html 加 print-pdf class
    // 触发 reveal.css 内置的打印样式（页面尺寸、page-break 等）
    document.documentElement.classList.add('print-pdf')
    document.body.classList.add('printing-slides')

    try { revealRef.current?.layout?.() } catch {}

    // 等待样式应用
    await new Promise(r => setTimeout(r, 300))

    // 触发浏览器打印对话框（用户选"另存为 PDF"）
    window.print()

    // 清理（打印对话框关闭后）
    setTimeout(() => {
      document.documentElement.classList.remove('print-pdf')
      document.body.classList.remove('printing-slides')
      try { revealRef.current?.layout?.() } catch {}
    }, 1000)
  }, [])

  const containerStyle: React.CSSProperties = fullscreen
    ? { width: '100%', height: '100%', background: '#f0f4f8', borderRadius: 0, position: 'relative' }
    : {
        width: '100%', aspectRatio: '16/10', background: '#f0f4f8',
        borderRadius: 16, overflow: 'hidden', position: 'relative',
        border: '1px solid rgba(203,213,225,0.6)',
        boxShadow: '0 8px 32px rgba(148,163,184,0.15), inset 0 1px 0 rgba(255,255,255,0.8)',
      }

  return (
    <div style={containerStyle}>
      <div ref={deckRef} className={`reveal theme-${style}`} style={{ width: '100%', height: '100%' }} />

      {/* 控制按钮 */}
      <div style={{
        position: 'absolute', bottom: 16, right: 16,
        display: 'flex', gap: 8, zIndex: 10,
      }}>
        {!fullscreen && (
          <button
            onClick={handleFullscreen}
            style={{
              padding: '8px 18px', borderRadius: 10, fontSize: 13, fontWeight: 600,
              background: 'linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%)',
              color: '#fff', border: 'none', cursor: 'pointer',
              boxShadow: '0 4px 12px rgba(37,99,235,0.3)',
            }}
          >
            全屏播放
          </button>
        )}
        {fullscreen && (
          <button
            onClick={handleExportPDF}
            style={{
              padding: '8px 18px', borderRadius: 10, fontSize: 13, fontWeight: 600,
              background: 'linear-gradient(135deg, #16a34a 0%, #15803d 100%)',
              color: '#fff', border: 'none', cursor: 'pointer',
              boxShadow: '0 4px 12px rgba(22,163,74,0.3)',
            }}
          >
            导出 PDF
          </button>
        )}
        {onClose && (
          <button
            onClick={onClose}
            style={{
              padding: '8px 18px', borderRadius: 10, fontSize: 13, fontWeight: 600,
              background: 'rgba(255,255,255,0.9)', color: '#475569',
              border: '1px solid rgba(203,213,225,0.8)', cursor: 'pointer',
              boxShadow: '0 2px 8px rgba(148,163,184,0.1)',
            }}
          >
            关闭
          </button>
        )}
      </div>

      <style>{`
        /* ===== 主题变量（默认 Python Blue） ===== */
        .reveal {
          --c-bg: linear-gradient(135deg, #ffffff 0%, #f8fafc 100%);
          --c-bg-present: linear-gradient(135deg, #ffffff 0%, #f0f7ff 100%);
          --c-text: #1e293b;
          --c-heading: #0f172a;
          --c-heading-grad: linear-gradient(135deg, #0f172a 0%, #1e40af 100%);
          --c-h2: #1e293b;
          --c-h3: #334155;
          --c-p: #475569;
          --c-li: #334155;
          --c-strong: #0f172a;
          --c-accent: #2563eb;
          --c-accent-light: #60a5fa;
          --c-bullet: linear-gradient(135deg, #2563eb 0%, #60a5fa 100%);
          --c-cover-grad: linear-gradient(135deg, #1e3a5f 0%, #1d4ed8 50%, #2563eb 100%);
          --c-cover-text: #ffffff;
          --c-cover-sub: rgba(255,255,255,0.85);
          --c-cover-body: rgba(255,255,255,0.75);
          --c-code-bg: #1e293b;
          --c-code-text: #e2e8f0;
          --c-code-inline-bg: rgba(37,99,235,0.08);
          --c-code-inline-text: #1e40af;
          --c-quote-bg: linear-gradient(135deg, rgba(37,99,235,0.06) 0%, rgba(96,165,250,0.08) 100%);
          --c-quote-border: #2563eb;
          --c-quote-text: #475569;
          --c-quote-shadow: inset 0 1px 0 rgba(37,99,235,0.1);
          --c-table-th: linear-gradient(135deg, #1e40af 0%, #2563eb 100%);
          --c-table-th-text: #ffffff;
          --c-table-td: #334155;
          --c-table-stripe: rgba(241,245,249,0.6);
          --c-border: rgba(203,213,225,0.5);
          --c-shadow: 0 2px 16px rgba(148,163,184,0.08);
          --c-pagenum: #94a3b8;
          --c-pagenum-bg: rgba(255,255,255,0.8);
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
          color: var(--c-text);
          background: var(--c-bg) !important;
        }

        /* 覆盖 reveal.js viewport 硬编码白色背景 */
        .reveal.reveal-viewport {
          background: var(--c-bg) !important;
          background-color: transparent !important;
        }
        /* slide-background 层（present 时 z-index:2 会盖住 section）强制透明 */
        .reveal .slide-background,
        .reveal .slide-background-content {
          background: transparent !important;
          background-color: transparent !important;
        }

        /* ===== Dark Premium 主题（黑底金调） ===== */
        .reveal.theme-dark-premium {
          --c-bg: linear-gradient(135deg, #0a0a0a 0%, #1a1a1a 100%);
          --c-bg-present: linear-gradient(135deg, #0f0f0f 0%, #1a1a1a 100%);
          --c-text: #e5e5e5;
          --c-heading: #ffffff;
          --c-heading-grad: linear-gradient(135deg, #ffffff 0%, #ffd700 100%);
          --c-h2: #f5f5f5;
          --c-h3: #d4d4d4;
          --c-p: #a3a3a3;
          --c-li: #d4d4d4;
          --c-strong: #ffffff;
          --c-accent: #ffd700;
          --c-accent-light: #fbbf24;
          --c-bullet: linear-gradient(135deg, #ffd700 0%, #fbbf24 100%);
          --c-cover-grad: linear-gradient(135deg, #000000 0%, #1a1a1a 50%, #0a0a0a 100%);
          --c-cover-text: #ffd700;
          --c-cover-sub: rgba(255,215,0,0.85);
          --c-cover-body: rgba(255,255,255,0.65);
          --c-code-bg: #000000;
          --c-code-text: #f5f5f5;
          --c-code-inline-bg: rgba(255,215,0,0.12);
          --c-code-inline-text: #ffd700;
          --c-quote-bg: linear-gradient(135deg, rgba(255,215,0,0.05) 0%, rgba(255,215,0,0.1) 100%);
          --c-quote-border: #ffd700;
          --c-quote-text: #d4d4d4;
          --c-quote-shadow: inset 0 1px 0 rgba(255,215,0,0.15);
          --c-table-th: linear-gradient(135deg, #262626 0%, #404040 100%);
          --c-table-th-text: #ffd700;
          --c-table-td: #d4d4d4;
          --c-table-stripe: rgba(255,255,255,0.03);
          --c-border: rgba(255,255,255,0.1);
          --c-shadow: 0 2px 16px rgba(0,0,0,0.4);
          --c-pagenum: #525252;
          --c-pagenum-bg: rgba(0,0,0,0.5);
        }

        /* ===== Keynote 主题（Apple 纯黑蓝调） ===== */
        .reveal.theme-keynote {
          --c-bg: #000000;
          --c-bg-present: #000000;
          --c-text: rgba(255,255,255,0.85);
          --c-heading: #ffffff;
          --c-heading-grad: linear-gradient(135deg, #ffffff 0%, #2997ff 100%);
          --c-h2: #ffffff;
          --c-h3: rgba(255,255,255,0.9);
          --c-p: rgba(255,255,255,0.75);
          --c-li: rgba(255,255,255,0.85);
          --c-strong: #ffffff;
          --c-accent: #2997ff;
          --c-accent-light: #60a5fa;
          --c-bullet: linear-gradient(135deg, #2997ff 0%, #60a5fa 100%);
          --c-cover-grad: #000000;
          --c-cover-text: #ffffff;
          --c-cover-sub: rgba(255,255,255,0.7);
          --c-cover-body: rgba(255,255,255,0.6);
          --c-code-bg: #1a1a1a;
          --c-code-text: #f5f5f5;
          --c-code-inline-bg: rgba(41,151,255,0.15);
          --c-code-inline-text: #2997ff;
          --c-quote-bg: rgba(255,255,255,0.05);
          --c-quote-border: #2997ff;
          --c-quote-text: rgba(255,255,255,0.85);
          --c-quote-shadow: inset 0 1px 0 rgba(255,255,255,0.08);
          --c-table-th: linear-gradient(135deg, #1a1a1a 0%, #2a2a2a 100%);
          --c-table-th-text: #2997ff;
          --c-table-td: rgba(255,255,255,0.9);
          --c-table-stripe: rgba(255,255,255,0.03);
          --c-border: rgba(255,255,255,0.15);
          --c-shadow: 0 2px 16px rgba(0,0,0,0.5);
          --c-pagenum: rgba(255,255,255,0.4);
          --c-pagenum-bg: rgba(0,0,0,0.4);
        }
        .reveal.theme-keynote .slides section {
          text-align: center;
        }
        .reveal.theme-keynote .slides section ul {
          display: inline-block;
          text-align: left;
        }

        /* ===== 基础排版 ===== */
        .reveal .slides {
          text-align: left;
        }
        .reveal .slides section {
          padding: 48px 56px;
          box-sizing: border-box;
          overflow: hidden;
          display: flex;
          flex-direction: column;
          justify-content: flex-start;
        }

        /* ===== 背景 ===== */
        .reveal .slides section {
          background: var(--c-bg);
          border-radius: 12px;
          box-shadow: var(--c-shadow);
        }
        .reveal .slides section.present {
          background: var(--c-bg-present);
        }

        /* ===== 封面页 ===== */
        .reveal .slides section.title-slide,
        .reveal .slides section:first-child {
          background: var(--c-cover-grad) !important;
          color: var(--c-cover-text) !important;
          text-align: center !important;
          display: flex !important;
          flex-direction: column !important;
          justify-content: center !important;
        }
        .reveal .slides section:first-child h1 {
          color: var(--c-cover-text) !important;
          font-size: 2.4em !important;
          font-weight: 800 !important;
          letter-spacing: -0.02em;
          margin-bottom: 16px !important;
          text-shadow: 0 2px 8px rgba(0,0,0,0.2);
          -webkit-text-fill-color: var(--c-cover-text) !important;
        }
        .reveal .slides section:first-child h3 {
          color: var(--c-cover-sub) !important;
          font-size: 1.1em !important;
          font-weight: 400 !important;
          margin-top: 0 !important;
        }
        .reveal .slides section:first-child p {
          color: var(--c-cover-body) !important;
        }

        /* ===== 标题 ===== */
        .reveal h1 {
          color: var(--c-heading);
          font-size: 2.2em;
          font-weight: 800;
          letter-spacing: -0.01em;
          margin-bottom: 24px;
          background: var(--c-heading-grad);
          -webkit-background-clip: text;
          -webkit-text-fill-color: transparent;
          background-clip: text;
        }
        .reveal h2 {
          color: var(--c-h2);
          font-size: 1.65em;
          font-weight: 700;
          margin-bottom: 22px;
          padding-bottom: 10px;
          border-bottom: 3px solid var(--c-accent);
          display: inline-block;
        }
        .reveal h3 {
          color: var(--c-h3);
          font-size: 1.3em;
          font-weight: 600;
          margin-bottom: 14px;
        }

        /* ===== 正文 ===== */
        .reveal p {
          color: var(--c-p);
          font-size: 1.05em;
          line-height: 1.7;
          margin-bottom: 12px;
        }
        .reveal li {
          color: var(--c-li);
          font-size: 1em;
          line-height: 1.75;
          margin-bottom: 8px;
        }
        .reveal ul {
          list-style: none;
          padding-left: 0;
        }
        .reveal ul li::before {
          content: "";
          display: inline-block;
          width: 9px;
          height: 9px;
          border-radius: 50%;
          background: var(--c-bullet);
          margin-right: 12px;
          vertical-align: middle;
          position: relative;
          top: -1px;
        }
        .reveal strong {
          color: var(--c-strong);
          font-weight: 700;
        }

        /* ===== 引用块 ===== */
        .reveal blockquote {
          background: var(--c-quote-bg);
          border-left: 4px solid var(--c-quote-border);
          border-radius: 0 10px 10px 0;
          padding: 14px 20px;
          margin: 16px 0;
          font-style: italic;
          color: var(--c-quote-text);
          box-shadow: var(--c-quote-shadow);
        }
        .reveal blockquote p {
          margin: 0;
          color: var(--c-quote-text);
        }

        /* ===== 代码块 ===== */
        .reveal pre {
          width: 100%;
          margin: 16px 0;
          border-radius: 12px;
          box-shadow: var(--c-shadow);
          border: 1px solid var(--c-border);
        }
        .reveal pre code {
          font-family: "JetBrains Mono", "Fira Code", "Cascadia Code", "Consolas", monospace;
          font-size: 0.85em;
          line-height: 1.6;
          padding: 20px 24px !important;
          border-radius: 12px;
          max-height: 440px;
          overflow: auto;
          background: var(--c-code-bg) !important;
          color: var(--c-code-text);
        }
        .reveal code {
          font-family: "JetBrains Mono", "Fira Code", "Consolas", monospace;
          font-size: 0.88em;
          background: var(--c-code-inline-bg);
          color: var(--c-code-inline-text);
          padding: 2px 6px;
          border-radius: 4px;
        }

        /* ===== 表格 ===== */
        .reveal table {
          width: 100%;
          border-collapse: collapse;
          margin: 16px 0;
          font-size: 0.85em;
          border-radius: 8px;
          overflow: hidden;
          box-shadow: var(--c-shadow);
        }
        .reveal table th {
          background: var(--c-table-th);
          color: var(--c-table-th-text);
          padding: 10px 16px;
          text-align: left;
          font-weight: 600;
        }
        .reveal table td {
          padding: 10px 16px;
          border-bottom: 1px solid var(--c-border);
          color: var(--c-table-td);
        }
        .reveal table tr:nth-child(even) td {
          background: var(--c-table-stripe);
        }

        /* ===== 页码与进度条 ===== */
        .reveal .slide-number {
          font-size: 12px;
          color: var(--c-pagenum);
          right: 16px;
          bottom: 16px;
          font-family: -apple-system, sans-serif;
          background: var(--c-pagenum-bg);
          padding: 4px 10px;
          border-radius: 6px;
        }
        .reveal .controls {
          color: var(--c-accent);
        }
        .reveal .progress {
          height: 3px;
          color: var(--c-accent);
        }

        .reveal .slides section > :last-child {
          margin-bottom: 0;
        }

        /* ===== 全屏适配 ===== */
        :fullscreen .reveal .slides section {
          border-radius: 0;
        }

        /* ===== PDF 导出打印样式 ===== */
        @media print {
          html.print-pdf,
          html.print-pdf body {
            background: #fff !important;
            margin: 0 !important;
            padding: 0 !important;
            height: auto !important;
            overflow: visible !important;
          }
          /* 隐藏页面所有非幻灯片内容（仍占位但不显示） */
          body.printing-slides * {
            visibility: hidden !important;
          }
          /* 只显示 reveal 及其子元素 */
          body.printing-slides .reveal,
          body.printing-slides .reveal * {
            visibility: visible !important;
          }
          /* reveal 绝对定位到左上角，占满打印页 */
          body.printing-slides .reveal {
            position: absolute !important;
            top: 0 !important;
            left: 0 !important;
            width: 1280px !important;
            min-height: 800px !important;
            background: #fff !important;
          }
          /* 每页幻灯片独立分页 */
          body.printing-slides .reveal .slides {
            display: block !important;
            margin: 0 !important;
            padding: 0 !important;
          }
          body.printing-slides .reveal .slides section {
            page-break-after: always !important;
            page-break-inside: avoid !important;
            position: relative !important;
            display: block !important;
            width: 1280px !important;
            height: 800px !important;
            overflow: hidden !important;
          }
          body.printing-slides .reveal .slides section:last-child {
            page-break-after: auto !important;
          }
          /* 打印时隐藏控制按钮 */
          body.printing-slides .reveal + div,
          body.printing-slides .reveal ~ div {
            display: none !important;
          }
        }
      `}</style>
    </div>
  )
}

export default SlidesViewer
