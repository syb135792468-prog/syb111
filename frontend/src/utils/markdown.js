import { marked } from 'marked'
import DOMPurify from 'dompurify'
import hljs from 'highlight.js'

// Configure marked
marked.setOptions({
  gfm: true,
  breaks: true,
  highlight: function (code, lang) {
    if (lang && hljs.getLanguage(lang)) {
      return hljs.highlight(code, { language: lang }).value
    }
    return hljs.highlightAuto(code).value
  },
})

export function renderMarkdown(text) {
  if (!text) return ''
  const raw = marked.parse(text)
  const clean = DOMPurify.sanitize(raw, {
    ADD_TAGS: ['svg', 'path', 'g', 'rect', 'circle', 'line', 'polyline', 'polygon', 'text', 'foreignObject'],
    ADD_ATTR: ['viewBox', 'd', 'fill', 'stroke', 'stroke-width', 'transform', 'cx', 'cy', 'r', 'x', 'y', 'width', 'height', 'points'],
  })
  return clean
}

export function highlightCodeBlocks(container) {
  const blocks = container.querySelectorAll('pre code')
  blocks.forEach((block) => {
    if (block.dataset.highlighted) return

    // Wrap in code-block-wrapper
    const pre = block.parentElement
    const wrapper = document.createElement('div')
    wrapper.className = 'code-block-wrapper'
    pre.parentNode.insertBefore(wrapper, pre)
    wrapper.appendChild(pre)

    // Add language label
    const lang = block.className.replace('language-', '').replace('hljs ', '')
    if (lang) {
      const header = document.createElement('div')
      header.className = 'flex items-center justify-between px-4 py-1.5 bg-[#161b22] text-gray-400 text-xs rounded-t-lg'
      header.innerHTML = `<span>${lang}</span>`
      wrapper.insertBefore(header, pre)
      pre.style.borderRadius = '0 0 8px 8px'
      pre.style.margin = '0'
    }

    // Add copy button
    const copyBtn = document.createElement('button')
    copyBtn.className = 'copy-btn'
    copyBtn.textContent = '复制'
    copyBtn.onclick = function () {
      navigator.clipboard.writeText(block.textContent).then(() => {
        copyBtn.textContent = '已复制'
        setTimeout(() => { copyBtn.textContent = '复制' }, 2000)
      })
    }
    wrapper.querySelector('.flex')?.appendChild(copyBtn)

    hljs.highlightElement(block)
    block.dataset.highlighted = 'true'
  })
}

export function escapeHtml(str) {
  const div = document.createElement('div')
  div.textContent = str
  return div.innerHTML
}
