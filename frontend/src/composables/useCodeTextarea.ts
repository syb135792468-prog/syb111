import { useCallback, type KeyboardEvent } from 'react'

const BRACKET_PAIRS: Record<string, string> = {
  '(': ')',
  '[': ']',
  '{': '}',
  "'": "'",
  '"': '"',
}

const CLOSING_BRACKETS = new Set(Object.values(BRACKET_PAIRS))

function getIndent(line: string): string {
  const match = line.match(/^(\s*)/)
  return match ? match[1] : ''
}

/**
 * 为纯 textarea 添加代码编辑便利功能：
 * - 括号/引号自动补全
 * - Tab 缩进 / Shift+Tab 反缩进
 * - Enter 自动缩进（保持当前缩进 + 冒号后额外缩进）
 */
export function useCodeTextarea(
  value: string,
  onChange: (val: string) => void
) {
  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      const el = e.currentTarget
      const { selectionStart: start, selectionEnd: end } = el

      // --- Tab / Shift+Tab 缩进 ---
      if (e.key === 'Tab') {
        e.preventDefault()
        if (e.shiftKey) {
          // 反缩进：移除当前行开头的最多4个空格
          const before = value.slice(0, start)
          const lineStart = before.lastIndexOf('\n') + 1
          const linePrefix = value.slice(lineStart, start)
          const spacesToRemove = linePrefix.match(/^ {1,4}/)?.[0].length ?? 0
          if (spacesToRemove > 0) {
            const newValue = value.slice(0, lineStart) + value.slice(lineStart + spacesToRemove)
            onChange(newValue)
            requestAnimationFrame(() => {
              el.selectionStart = el.selectionEnd = Math.max(start - spacesToRemove, lineStart)
            })
          }
        } else {
          // 正向缩进：插入4个空格
          const newValue = value.slice(0, start) + '    ' + value.slice(end)
          onChange(newValue)
          requestAnimationFrame(() => {
            el.selectionStart = el.selectionEnd = start + 4
          })
        }
        return
      }

      // --- 括号/引号自动补全 ---
      if (BRACKET_PAIRS[e.key]) {
        // 有选中文本时：用括号包裹选中内容
        if (start !== end) {
          e.preventDefault()
          const open = e.key
          const close = BRACKET_PAIRS[open]
          const newValue = value.slice(0, start) + open + value.slice(start, end) + close + value.slice(end)
          onChange(newValue)
          requestAnimationFrame(() => {
            el.selectionStart = start + 1
            el.selectionEnd = end + 1
          })
          return
        }

        // 引号：如果下一个字符已经是同类引号，跳过而不是重复插入
        if ((e.key === "'" || e.key === '"') && value[end] === e.key) {
          e.preventDefault()
          requestAnimationFrame(() => {
            el.selectionStart = el.selectionEnd = end + 1
          })
          return
        }

        // 自动补全：插入开括号+闭括号，光标在中间
        e.preventDefault()
        const close = BRACKET_PAIRS[e.key]
        const newValue = value.slice(0, start) + e.key + close + value.slice(end)
        onChange(newValue)
        requestAnimationFrame(() => {
          el.selectionStart = el.selectionEnd = start + 1
        })
        return
      }

      // --- 输入闭括号时跳过（如果下一个字符就是它）---
      if (CLOSING_BRACKETS.has(e.key) && value[start] === e.key) {
        e.preventDefault()
        requestAnimationFrame(() => {
          el.selectionStart = el.selectionEnd = start + 1
        })
        return
      }

      // --- Backspace 删除配对括号 ---
      if (e.key === 'Backspace' && start === end && start > 0) {
        const charBefore = value[start - 1]
        const charAfter = value[start]
        if (BRACKET_PAIRS[charBefore] === charAfter) {
          e.preventDefault()
          const newValue = value.slice(0, start - 1) + value.slice(start + 1)
          onChange(newValue)
          requestAnimationFrame(() => {
            el.selectionStart = el.selectionEnd = start - 1
          })
          return
        }
      }

      // --- Enter 自动缩进 ---
      if (e.key === 'Enter') {
        e.preventDefault()
        const before = value.slice(0, start)
        const after = value.slice(end)
        const currentLine = before.slice(before.lastIndexOf('\n') + 1)
        const indent = getIndent(currentLine)
        const charBeforeCursor = value[start - 1]
        const extraIndent = charBeforeCursor === ':' ? '    ' : ''
        const insertion = '\n' + indent + extraIndent
        const newValue = before + insertion + after
        onChange(newValue)
        requestAnimationFrame(() => {
          el.selectionStart = el.selectionEnd = start + insertion.length
        })
        return
      }
    },
    [value, onChange]
  )

  return { handleKeyDown }
}
