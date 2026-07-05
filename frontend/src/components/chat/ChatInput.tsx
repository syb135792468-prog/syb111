import React, { useState, useRef, useCallback, useEffect, useImperativeHandle, forwardRef } from 'react'
import { Send, Square, Image as ImageIcon, X, Loader2, Paperclip } from 'lucide-react'
import { uploadImage, ImageUploadResult } from '../../api/images'
import { useAppStore } from '../../stores/app'

interface PendingImage {
  id: string
  file: File
  preview: string
  result?: ImageUploadResult
  uploading: boolean
  error?: string
}

interface ChatInputProps {
  isStreaming?: boolean
  placeholder?: string
  onSend: (text: string, imageUrls?: string[]) => void
  onAbort: () => void
}

export interface ChatInputHandle {
  focus: () => void
}

const DEFAULT_PLACEHOLDER = '输入你的问题...'
const ALLOWED_TYPES = ['image/png', 'image/jpeg', 'image/gif', 'image/webp']
const MAX_FILE_SIZE = 10 * 1024 * 1024

const ChatInput = forwardRef<ChatInputHandle, ChatInputProps>(
  ({ isStreaming = false, placeholder = '', onSend, onAbort }, ref) => {
    const [message, setMessage] = useState('')
    const [pendingImages, setPendingImages] = useState<PendingImage[]>([])
    const [isDragOver, setIsDragOver] = useState(false)
    const textareaRef = useRef<HTMLTextAreaElement>(null)
    const fileInputRef = useRef<HTMLInputElement>(null)
    const pendingImagesRef = useRef<PendingImage[]>([])
    const showToast = useAppStore((state) => state.showToast)

    const currentPlaceholder = placeholder || DEFAULT_PLACEHOLDER
    const trimmed = message.trim()
    const hasUploading = pendingImages.some((image) => image.uploading)
    const canSend = (trimmed || pendingImages.length > 0) && !hasUploading

    useImperativeHandle(
      ref,
      () => ({
        focus: () => {
          requestAnimationFrame(() => textareaRef.current?.focus())
        },
      }),
      [],
    )

    const adjustHeight = useCallback(() => {
      const element = textareaRef.current
      if (!element) return
      element.style.height = 'auto'
      element.style.height = `${Math.min(element.scrollHeight, 120)}px`
    }, [])

    const handleFiles = useCallback(
      async (files: FileList | File[]) => {
        const fileArray = Array.from(files)
        const validFiles = fileArray.filter((file) => {
          if (!ALLOWED_TYPES.includes(file.type)) {
            showToast(`不支持的文件类型：${file.name}，仅支持 PNG/JPG/GIF/WebP`, 'error')
            return false
          }
          if (file.size > MAX_FILE_SIZE) {
            showToast(`文件过大：${file.name}，最大支持 10MB`, 'error')
            return false
          }
          return true
        })

        if (validFiles.length === 0) return

        const newImages: PendingImage[] = validFiles.map((file) => ({
          id: crypto.randomUUID(),
          file,
          preview: URL.createObjectURL(file),
          uploading: true,
        }))

        setPendingImages((prev) => [...prev, ...newImages])

        for (const image of newImages) {
          try {
            const result = await uploadImage(image.file)
            setPendingImages((prev) =>
              prev.map((item) => (item.id === image.id ? { ...item, result, uploading: false } : item)),
            )
          } catch (error: unknown) {
            const errorMessage = error instanceof Error ? error.message : '上传失败'
            setPendingImages((prev) =>
              prev.map((item) => (item.id === image.id ? { ...item, uploading: false, error: errorMessage } : item)),
            )
          }
        }
      },
      [showToast],
    )

    const removeImage = useCallback((id: string) => {
      setPendingImages((prev) => {
        const image = prev.find((item) => item.id === id)
        if (image) URL.revokeObjectURL(image.preview)
        return prev.filter((item) => item.id !== id)
      })
    }, [])

    const retryImage = useCallback(async (image: PendingImage) => {
      setPendingImages((prev) =>
        prev.map((item) => (item.id === image.id ? { ...item, uploading: true, error: undefined } : item)),
      )

      try {
        const result = await uploadImage(image.file)
        setPendingImages((prev) =>
          prev.map((item) => (item.id === image.id ? { ...item, result, uploading: false } : item)),
        )
      } catch (error: unknown) {
        const errorMessage = error instanceof Error ? error.message : '上传失败'
        setPendingImages((prev) =>
          prev.map((item) => (item.id === image.id ? { ...item, uploading: false, error: errorMessage } : item)),
        )
      }
    }, [])

    const handleSend = useCallback(() => {
      const text = message.trim()
      if (!text && pendingImages.length === 0) return
      if (hasUploading || isStreaming) return

      const failedCount = pendingImages.filter((image) => image.error).length
      if (failedCount > 0) {
        showToast(`还有 ${failedCount} 张图片上传失败，请移除或重试`, 'error')
        return
      }

      const imageUrls = pendingImages.filter((image) => image.result).map((image) => image.result!.url)
      onSend(text, imageUrls.length > 0 ? imageUrls : undefined)
      setMessage('')
      pendingImages.forEach((image) => URL.revokeObjectURL(image.preview))
      setPendingImages([])
      requestAnimationFrame(adjustHeight)
    }, [message, pendingImages, hasUploading, isStreaming, onSend, adjustHeight, showToast])

    const handleKeydown = useCallback(
      (event: React.KeyboardEvent) => {
        if (event.nativeEvent.isComposing) return
        if (event.key === 'Enter' && !event.shiftKey) {
          event.preventDefault()
          handleSend()
        }
      },
      [handleSend],
    )

    const handleDragOver = useCallback((event: React.DragEvent) => {
      event.preventDefault()
      event.stopPropagation()
      setIsDragOver(true)
    }, [])

    const handleDragLeave = useCallback((event: React.DragEvent) => {
      event.preventDefault()
      event.stopPropagation()
      const related = event.relatedTarget as Node | null
      if (related && event.currentTarget.contains(related)) return
      setIsDragOver(false)
    }, [])

    const handleDrop = useCallback(
      (event: React.DragEvent) => {
        event.preventDefault()
        event.stopPropagation()
        setIsDragOver(false)
        if (event.dataTransfer.files.length > 0) {
          handleFiles(event.dataTransfer.files)
        }
      },
      [handleFiles],
    )

    const handlePaste = useCallback(
      (event: React.ClipboardEvent) => {
        const items = event.clipboardData.items
        const imageFiles: File[] = []

        for (let index = 0; index < items.length; index += 1) {
          if (items[index].type.startsWith('image/')) {
            const file = items[index].getAsFile()
            if (file) imageFiles.push(file)
          }
        }

        if (imageFiles.length > 0) {
          event.preventDefault()
          handleFiles(imageFiles)
        }
      },
      [handleFiles],
    )

    useEffect(() => {
      adjustHeight()
    }, [placeholder, adjustHeight])

    useEffect(() => {
      pendingImagesRef.current = pendingImages
    }, [pendingImages])

    useEffect(() => {
      return () => {
        pendingImagesRef.current.forEach((image) => URL.revokeObjectURL(image.preview))
      }
    }, [])

    return (
      <div className="chat-composer-shell">
        <div
          className={`chat-composer-input ${isDragOver ? 'drag-over' : ''}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          style={{
            position: 'relative',
            borderColor: isDragOver ? 'var(--py-yellow)' : 'rgba(112, 137, 175, 0.14)',
            boxShadow: isDragOver ? '0 0 0 4px rgba(255, 212, 59, 0.16)' : 'inset 0 1px 0 rgba(255,255,255,0.78)',
          }}
        >
          {isDragOver && (
            <div
              style={{
                position: 'absolute',
                inset: 0,
                borderRadius: 18,
                background: 'rgba(255, 212, 59, 0.08)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                zIndex: 4,
                pointerEvents: 'none',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--py-yellow-deep)', fontWeight: 700 }}>
                <Paperclip style={{ width: 17, height: 17 }} />
                松开即可上传图片
              </div>
            </div>
          )}

          {pendingImages.length > 0 && (
            <div style={{ display: 'flex', gap: 10, marginBottom: 10, flexWrap: 'wrap' }}>
              {pendingImages.map((image) => (
                <div key={image.id} style={{ position: 'relative', width: 78, height: 78 }}>
                  <img
                    src={image.preview}
                    alt="preview"
                    style={{
                      width: 78,
                      height: 78,
                      objectFit: 'cover',
                      borderRadius: 16,
                      border: image.error ? '2px solid #ef4444' : '1px solid rgba(112, 137, 175, 0.16)',
                      opacity: image.uploading ? 0.56 : 1,
                    }}
                  />

                  {image.uploading && (
                    <div
                      style={{
                        position: 'absolute',
                        inset: 0,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                      }}
                    >
                      <Loader2 style={{ width: 20, height: 20, color: 'var(--py-blue)', animation: 'spin 1s linear infinite' }} />
                    </div>
                  )}

                  {image.error && (
                    <button
                      type="button"
                      onClick={() => retryImage(image)}
                      style={{
                        position: 'absolute',
                        inset: 0,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        background: 'rgba(239,68,68,0.86)',
                        color: '#ffffff',
                        border: 'none',
                        borderRadius: 16,
                        cursor: 'pointer',
                        fontSize: 11,
                        fontWeight: 600,
                      }}
                      title={`上传失败：${image.error}，点击重试`}
                    >
                      点击重试
                    </button>
                  )}

                  <button
                    type="button"
                    onClick={() => removeImage(image.id)}
                    aria-label="移除图片"
                    style={{
                      position: 'absolute',
                      top: 4,
                      right: 4,
                      width: 20,
                      height: 20,
                      borderRadius: '50%',
                      background: '#ef4444',
                      color: '#fff',
                      border: 'none',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      cursor: 'pointer',
                    }}
                  >
                    <X style={{ width: 12, height: 12 }} />
                  </button>
                </div>
              ))}
            </div>
          )}

          <form onSubmit={(event) => { event.preventDefault(); handleSend() }} style={{ display: 'flex', alignItems: 'flex-end', gap: 10 }}>
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="shell-icon-button btn-click-feedback"
              title="上传图片，也支持粘贴和拖拽"
              style={{ width: 38, height: 38, borderRadius: 12 }}
            >
              <ImageIcon style={{ width: 17, height: 17 }} />
            </button>

            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/gif,image/webp"
              multiple
              style={{ display: 'none' }}
              onChange={(event) => {
                if (event.target.files && event.target.files.length > 0) {
                  handleFiles(event.target.files)
                  event.target.value = ''
                }
              }}
            />

            <textarea
              ref={textareaRef}
              value={message}
              onChange={(event) => setMessage(event.target.value)}
              onKeyDown={handleKeydown}
              onInput={adjustHeight}
              onPaste={handlePaste}
              placeholder={currentPlaceholder}
              aria-label="消息输入框"
              rows={1}
              style={{
                flex: 1,
                background: 'transparent',
                border: 'none',
                outline: 'none',
                resize: 'none',
                color: 'var(--ink)',
                fontSize: 15,
                lineHeight: 1.65,
                minHeight: 24,
                maxHeight: 120,
                fontFamily: 'inherit',
              }}
            />

            {isStreaming ? (
              <button
                type="button"
                onClick={onAbort}
                className="btn-click-feedback"
                aria-label="停止生成"
                style={{
                  width: 40,
                  height: 40,
                  borderRadius: 14,
                  border: 'none',
                  background: '#ef4444',
                  color: '#ffffff',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  boxShadow: '0 18px 36px rgba(239,68,68,0.18)',
                }}
              >
                <Square style={{ width: 15, height: 15 }} />
              </button>
            ) : (
              <button
                type="submit"
                disabled={!canSend}
                className="btn-click-feedback"
                aria-label="发送消息"
                style={{
                  width: 42,
                  height: 42,
                  borderRadius: 15,
                  border: '1px solid rgba(48, 105, 152, 0.18)',
                  background: canSend
                    ? 'linear-gradient(135deg, rgba(48,105,152,0.96), rgba(38,84,121,0.98))'
                    : 'rgba(145, 160, 186, 0.68)',
                  color: '#ffffff',
                  cursor: canSend ? 'pointer' : 'not-allowed',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  boxShadow: canSend ? '0 18px 36px rgba(48, 105, 152, 0.18)' : 'none',
                }}
              >
                <Send style={{ width: 16, height: 16 }} />
              </button>
            )}
          </form>
        </div>
      </div>
    )
  },
)

ChatInput.displayName = 'ChatInput'

export default ChatInput
