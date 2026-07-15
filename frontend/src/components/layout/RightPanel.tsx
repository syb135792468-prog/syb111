import React, { lazy, Suspense, useState, useCallback, useRef } from 'react'
import { useAppStore } from '../../stores/app'
import { useIsMobile } from '../../hooks/useIsMobile'
import { Loader2, PanelRightOpen, RefreshCw, ChevronLeft, PanelRightClose, History } from 'lucide-react'

const ChatExplainPanel = lazy(() => import('../panels/ChatExplainPanel'))
const PathDetailPanel = lazy(() => import('../panels/PathDetailPanel'))
const MindmapDetailPanel = lazy(() => import('../panels/MindmapDetailPanel'))
const ErrorDetailPanel = lazy(() => import('../panels/ErrorDetailPanel'))
const AnalysisDetailPanel = lazy(() => import('../panels/AnalysisDetailPanel'))
const CodeExplainPanel = lazy(() => import('../panels/CodeExplainPanel'))
const ChallengeSolutionPanel = lazy(() => import('../panels/ChallengeSolutionPanel'))
const ResourceSummaryPanel = lazy(() => import('../panels/ResourceSummaryPanel'))
const AISuggestionPanel = lazy(() => import('../panels/AISuggestionPanel'))
const AnimationDetailPanel = lazy(() => import('../panels/AnimationDetailPanel'))

const panelComponents: Record<string, React.LazyExoticComponent<React.FC>> = {
  'chat-explain': ChatExplainPanel,
  'path-detail': PathDetailPanel,
  'mindmap-detail': MindmapDetailPanel,
  'error-detail': ErrorDetailPanel,
  'analysis-detail': AnalysisDetailPanel,
  'code-explain': CodeExplainPanel,
  'challenge-solution': ChallengeSolutionPanel,
  'resource-summary': ResourceSummaryPanel,
  'ai-suggestion': AISuggestionPanel,
  'animation-detail': AnimationDetailPanel,
}

const panelTitles: Record<string, string> = {
  'chat-explain': '内容详解',
  'path-detail': '知识点详情',
  'mindmap-detail': '知识点详情',
  'error-detail': '错题讲解',
  'analysis-detail': '分析详情',
  'code-explain': '代码解释',
  'challenge-solution': '解题思路',
  'resource-summary': '资源详情',
  'ai-suggestion': '学习建议',
  'animation-detail': '动画详情',
}

const PanelLoading: React.FC = () => (
  <div className="flex items-center justify-center h-32">
    <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--mute)', fontSize: 12 }}>
      <Loader2 className="w-4 h-4 animate-spin" style={{ color: 'var(--py-blue)' }} />
      正在载入内容...
    </div>
  </div>
)

const DefaultPanel: React.FC = () => (
  <div className="flex h-full items-center justify-center px-5 py-6">
    <div style={{ textAlign: 'center', maxWidth: 240 }}>
      <div
        style={{
          width: 52,
          height: 52,
          borderRadius: 16,
          margin: '0 auto 12px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: 'rgba(48, 105, 152, 0.08)',
          border: '1px solid rgba(48, 105, 152, 0.12)',
        }}
      >
        <PanelRightOpen className="h-6 w-6" style={{ color: 'var(--py-blue)' }} />
      </div>
      <p style={{ margin: '0 0 6px', color: 'var(--ink)', fontSize: 14, fontWeight: 600 }}>这里显示辅助说明</p>
      <p style={{ margin: 0, color: 'var(--mute)', fontSize: 12, lineHeight: 1.7 }}>
        点击对话、路径或资源内容后，这里会展开更深入的解释。
      </p>
    </div>
  </div>
)

const RightPanel: React.FC = () => {
  const { isOpen, isCollapsed, width, type, routeKey, historyByRoute, currentIndexByRoute } = useAppStore((state) => state.rightPanel)
  const setRightPanelHistoryIndex = useAppStore((state) => state.setRightPanelHistoryIndex)
  const toggleRightPanelCollapse = useAppStore((state) => state.toggleRightPanelCollapse)
  const setRightPanelWidth = useAppStore((state) => state.setRightPanelWidth)
  const closeRightPanel = useAppStore((state) => state.closeRightPanel)
  const isMobile = useIsMobile()

  const PanelComponent = type ? panelComponents[type] : null
  const panelTitle = type ? (panelTitles[type] || '详情') : '辅助说明'
  const routeHistory = historyByRoute[routeKey] || []
  const currentIndex = currentIndexByRoute[routeKey] ?? -1

  const [activeTab, setActiveTab] = useState<'detail' | 'history'>('detail')
  const dragRef = useRef<{ startX: number; startWidth: number } | null>(null)

  const handleMouseDown = useCallback(
    (event: React.MouseEvent) => {
      event.preventDefault()
      dragRef.current = { startX: event.clientX, startWidth: width }

      const handleMouseMove = (moveEvent: MouseEvent) => {
        if (!dragRef.current) return
        const delta = dragRef.current.startX - moveEvent.clientX
        setRightPanelWidth(dragRef.current.startWidth + delta)
      }

      const handleMouseUp = () => {
        dragRef.current = null
        document.removeEventListener('mousemove', handleMouseMove)
        document.removeEventListener('mouseup', handleMouseUp)
        document.body.style.cursor = ''
        document.body.style.userSelect = ''
      }

      document.addEventListener('mousemove', handleMouseMove)
      document.addEventListener('mouseup', handleMouseUp)
      document.body.style.cursor = 'col-resize'
      document.body.style.userSelect = 'none'
    },
    [width, setRightPanelWidth],
  )

  const effectiveOpen = isOpen && !isCollapsed

  return (
    <>
      {!isMobile && isOpen && isCollapsed && (
        <button
          onClick={toggleRightPanelCollapse}
          className="rail-collapse-button btn-click-feedback"
          title="展开辅助说明"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
      )}

      {isMobile && effectiveOpen && (
        <div
          onClick={closeRightPanel}
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15, 23, 42, 0.18)',
            backdropFilter: 'blur(3px)',
            zIndex: 40,
          }}
        />
      )}

      <aside
        className="right-panel-shell h-full flex-shrink-0 overflow-hidden relative"
        style={
          isMobile
            ? {
                position: 'fixed',
                right: 0,
                top: 0,
                bottom: 0,
                zIndex: 50,
                width: effectiveOpen ? '100%' : 0,
                transition: 'width 0.25s ease',
              }
            : {
                width: effectiveOpen ? width : 0,
                transition: dragRef.current ? 'none' : 'width 0.25s ease',
              }
        }
      >
        {effectiveOpen && (
          <div style={{ width: isMobile ? '100%' : width, height: '100%', padding: '14px 12px 12px' }}>
            {!isMobile && (
              <div
                onMouseDown={handleMouseDown}
                style={{
                  position: 'absolute',
                  left: 0,
                  top: 0,
                  bottom: 0,
                  width: 8,
                  cursor: 'col-resize',
                  zIndex: 10,
                }}
              />
            )}

            <div className="rail-card" style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
              <div
                style={{
                  padding: '14px 14px 12px',
                  borderBottom: '1px solid rgba(112, 137, 175, 0.12)',
                  display: 'flex',
                  alignItems: 'flex-start',
                  justifyContent: 'space-between',
                  gap: 12,
                }}
              >
                <div style={{ minWidth: 0 }}>
                  <div
                    style={{
                      color: 'var(--ink)',
                      fontSize: 17,
                      fontWeight: 700,
                      lineHeight: 1.2,
                      letterSpacing: '-0.02em',
                    }}
                  >
                    {panelTitle}
                  </div>
                  <div style={{ color: 'var(--mute)', fontSize: 11.5, marginTop: 4, lineHeight: 1.65 }}>
                    作为主界面的补充说明区，不抢主视觉。
                  </div>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                  <button
                    onClick={() => {
                      const store = useAppStore.getState()
                      const data = store.rightPanel.data
                      if (data?.onPreview) (data.onPreview as () => void)()
                    }}
                    className="rail-icon-button"
                    title="刷新内容"
                  >
                    <RefreshCw size={15} />
                  </button>
                  <button
                    onClick={isMobile ? closeRightPanel : toggleRightPanelCollapse}
                    className="rail-icon-button"
                    title="收起面板"
                  >
                    <PanelRightClose size={15} />
                  </button>
                </div>
              </div>

              <div style={{ padding: '10px 10px 0', display: 'flex', gap: 8 }}>
                <button
                  onClick={() => setActiveTab('detail')}
                  className={`rail-tab ${activeTab === 'detail' ? 'rail-tab-active' : ''}`}
                >
                  当前说明
                </button>
                <button
                  onClick={() => setActiveTab('history')}
                  className={`rail-tab ${activeTab === 'history' ? 'rail-tab-active' : ''}`}
                >
                  <History style={{ width: 13, height: 13 }} />
                  历史片段
                  {routeHistory.length > 0 ? ` ${routeHistory.length}` : ''}
                </button>
              </div>

              <div className="flex-1 overflow-y-auto" style={{ padding: '10px' }}>
                {activeTab === 'detail' ? (
                  <div className="rail-inner-surface">
                    {PanelComponent ? (
                      <Suspense fallback={<PanelLoading />}>
                        <PanelComponent />
                      </Suspense>
                    ) : (
                      <DefaultPanel />
                    )}
                  </div>
                ) : (
                  <div className="rail-inner-surface" style={{ padding: 0, overflow: 'hidden' }}>
                    {routeHistory.length === 0 ? (
                      <div className="rail-empty" style={{ minHeight: 180 }}>
                        暂无历史记录
                      </div>
                    ) : (
                      routeHistory.map((entry, index) => {
                        const active = index === currentIndex
                        return (
                          <button
                            key={entry.id}
                            onClick={() => setRightPanelHistoryIndex(index)}
                            className={`rail-history-item ${active ? 'rail-history-item-active' : ''}`}
                          >
                            <div
                              style={{
                                fontSize: 13,
                                fontWeight: active ? 700 : 600,
                                color: active ? 'var(--py-blue-deep)' : 'var(--ink-soft)',
                                marginBottom: 4,
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap',
                              }}
                            >
                              {entry.label}
                            </div>
                            <div style={{ fontSize: 11, color: 'var(--faint)' }}>
                              {new Date(entry.createdAt).toLocaleString('zh-CN', {
                                month: 'numeric',
                                day: 'numeric',
                                hour: '2-digit',
                                minute: '2-digit',
                              })}
                            </div>
                          </button>
                        )
                      })
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </aside>
    </>
  )
}

export default RightPanel
