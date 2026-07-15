import React from 'react'
import { renderMarkdown } from '../../utils/markdown'

interface MarkdownTextProps {
  content: string
  className?: string
}

const MarkdownText: React.FC<MarkdownTextProps> = ({ content, className }) => {
  const html = renderMarkdown(content || '')
  return (
    <div
      className={`md-content ${className || ''}`.trim()}
      style={{ fontSize: 'inherit', lineHeight: 'inherit', color: 'inherit' }}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  )
}

export default MarkdownText
