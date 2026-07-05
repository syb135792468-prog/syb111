import { Marked } from 'marked'
import { markedHighlight } from 'marked-highlight'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js'

const marked = new Marked(
  markedHighlight({
    langPrefix: 'hljs language-',
    highlight(code: string, lang: string) {
      if (lang && hljs.getLanguage(lang)) {
        return hljs.highlight(code, { language: lang }).value
      }
      return hljs.highlightAuto(code).value
    },
  }),
  { gfm: true, breaks: true }
)

export function renderMarkdown(text: string): string {
  if (!text) return ''
  const raw = marked.parse(text) as string
  const clean = DOMPurify.sanitize(raw, {
    ADD_TAGS: ['svg', 'path', 'g', 'rect', 'circle', 'line', 'polyline', 'polygon', 'text'],
    ADD_ATTR: ['viewBox', 'd', 'fill', 'stroke', 'stroke-width', 'transform', 'cx', 'cy', 'r', 'x', 'y', 'width', 'height', 'points'],
  })
  return clean
}

export function highlightCodeBlocks(container: HTMLElement): void {
  const blocks = container.querySelectorAll('pre code')
  blocks.forEach((block) => {
    if ((block as HTMLElement).dataset.highlighted) return

    const pre = block.parentElement!
    const wrapper = document.createElement('div')
    wrapper.className = 'code-block-wrapper'
    pre.parentNode!.insertBefore(wrapper, pre)
    wrapper.appendChild(pre)

    const lang = block.className.replace('language-', '').replace('hljs ', '').replace('hljs', '').trim()
    const lineCount = block.textContent?.split('\n').length || 0
    const header = document.createElement('div')
    header.className = 'code-header'
    header.innerHTML = `<span class="lang-label"><span>${lang || '代码'}</span><span class="line-count">${lineCount} 行</span></span>`
    wrapper.insertBefore(header, pre)
    pre.style.borderRadius = '0'
    pre.style.margin = '0'

    const copyBtn = document.createElement('button')
    copyBtn.className = 'copy-btn'
    copyBtn.textContent = '复制'
    copyBtn.onclick = function () {
      // 克隆节点，去掉 <br> 标签（防止 marked breaks:true 注入的多余换行）
      const clone = block.cloneNode(true) as HTMLElement
      clone.querySelectorAll('br').forEach(br => br.remove())
      const text = clone.textContent || ''
      navigator.clipboard.writeText(text).then(() => {
        copyBtn.textContent = '已复制'
        copyBtn.classList.add('copied')
        setTimeout(() => {
          copyBtn.textContent = '复制'
          copyBtn.classList.remove('copied')
        }, 2000)
      })
    }
    header.appendChild(copyBtn)

    ;(block as HTMLElement).dataset.highlighted = 'true'
  })
}

export function escapeHtml(str: string): string {
  const div = document.createElement('div')
  div.textContent = str
  return div.innerHTML
}

export function highlightCodeToHtml(code: string, lang?: string): string {
  if (!code) return ''
  try {
    const language = lang || 'python'
    if (hljs.getLanguage(language)) {
      return hljs.highlight(code, { language }).value
    }
    return hljs.highlightAuto(code).value
  } catch {
    return escapeHtml(code)
  }
}
