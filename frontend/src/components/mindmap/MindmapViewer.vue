<script setup>
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import MindElixir from 'mind-elixir'
import 'mind-elixir/style.css'

const props = defineProps({
  content: { type: String, default: '' },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['select'])

const mapRef = ref(null)
const zoomLevel = ref(100)
const detailNode = ref(null)
const showDetail = ref(false)
const renderError = ref('')

let mind = null
let selectHandler = null
let expandHandler = null
let scaleHandler = null

// Metadata backup: id → metadata (in case MindElixir strips custom fields)
const metadataMap = new Map()

// ===== 自定义主题 =====
const THEME = {
  name: 'PythonHelper',
  palette: [
    '#3b82f6', '#8b5cf6', '#10b981', '#f59e0b',
    '#ef4444', '#06b6d4', '#ec4899', '#84cc16',
  ],
  cssVar: {
    '--main-color': '#ffffff',
    '--main-bgcolor': '#7c3aed',
    '--main-bgcolor-transparent': 'rgba(124, 58, 237, 0.8)',
    '--color': '#1e293b',
    '--bgcolor': '#f8fafc',
    '--root-color': '#ffffff',
    '--root-bgcolor': '#1e40af',
    '--root-border-color': '#1e3a8a',
    '--root-radius': '14px',
    '--main-radius': '10px',
    '--selected': '#3b82f6',
    '--accent-color': '#3b82f6',
    '--node-gap-x': '20px',
    '--node-gap-y': '8px',
    '--main-gap-x': '60px',
    '--main-gap-y': '16px',
    '--topic-padding': '10px 18px',
    '--panel-color': '#1e293b',
    '--panel-bgcolor': '#ffffff',
    '--panel-border-color': '#e2e8f0',
    '--map-padding': '50px 80px',
  },
}

// ===== 内容检测与解析 =====
function detectContentType(text) {
  if (!text) return 'empty'
  const trimmed = text.trim()
  if (trimmed.startsWith('{') && trimmed.includes('nodeData')) return 'json'
  try {
    const parsed = JSON.parse(trimmed)
    if (parsed.nodeData) return 'json'
  } catch {}
  if (/^(graph|flowchart|sequenceDiagram|classDiagram|stateDiagram|pie|gantt|erDiagram|mindmap)\b/i.test(trimmed)) return 'mermaid'
  if (/^#+\s/.test(trimmed) || /^-\s/m.test(trimmed)) return 'markdown'
  return 'unknown'
}

// ===== JSON → MindElixir 数据转换 =====
function jsonToMindElixir(jsonStr) {
  try {
    const data = JSON.parse(jsonStr.trim())
    const nodeData = data.nodeData || data
    return convertNode(nodeData, 0)
  } catch (e) {
    return null
  }
}

function convertNode(node, level) {
  const id = node.id || `node_${Math.random().toString(36).slice(2, 9)}`
  const result = {
    id,
    topic: node.topic || node.text || '未命名',
    expanded: level < 2,  // 默认展开前2层
    children: [],
  }

  // 存储详细数据到 metadata（MindElixir 支持 metadata 字段）
  const meta = {
    definition: node.definition || '',
    syntax: node.syntax || '',
    examples: node.examples || [],
    pitfalls: node.pitfalls || [],
    advice: node.advice || '',
  }
  result.metadata = meta
  metadataMap.set(id, meta)  // backup in case MindElixir strips it

  // 根节点样式
  if (level === 0) {
    result.style = {
      fontSize: '20',
      color: '#ffffff',
      background: '#1e40af',
      fontWeight: 'bold',
    }
  } else if (level === 1) {
    result.style = {
      fontSize: '15',
      color: '#ffffff',
      background: '#7c3aed',
      fontWeight: '600',
    }
    result.branchColor = '#a78bfa'
  } else if (level === 2) {
    result.style = {
      fontSize: '13',
      color: '#1e293b',
      background: '#ffffff',
      fontWeight: '500',
      border: '1.5px solid #e2e8f0',
    }
    result.branchColor = '#cbd5e1'
  } else {
    result.style = {
      fontSize: '12',
      color: '#475569',
      background: '#f8fafc',
      border: '1px solid #e2e8f0',
    }
    result.branchColor = '#e2e8f0'
  }

  // 递归子节点
  if (node.children && node.children.length > 0) {
    result.children = node.children.map(c => convertNode(c, level + 1))
  }

  return result
}

// ===== Mermaid → MindElixir 数据转换 =====
function mermaidToMindElixir(mermaidStr) {
  const lines = mermaidStr.split('\n').filter(l => {
    const t = l.trim()
    return t && !t.startsWith('graph') && !t.startsWith('flowchart') && !t.startsWith('%%')
  })

  const nodeText = new Map()
  const childrenMap = new Map()
  const allChildren = new Set()
  const allParents = new Set()
  const lineOrder = []

  function ensureId(id) {
    if (!lineOrder.includes(id)) lineOrder.push(id)
  }

  for (const line of lines) {
    const arrowRe = /(\w+)(?:\["?([^"\]]*)"?\])?\s*(?:-->|-->>|-\.-|--)\s*(\w+)(?:\["?([^"\]]*)"?\])?/g
    let m
    while ((m = arrowRe.exec(line)) !== null) {
      const [, fromId, fromLabel, toId, toLabel] = m
      if (fromLabel) nodeText.set(fromId, fromLabel)
      if (toLabel) nodeText.set(toId, toLabel)
      if (!childrenMap.has(fromId)) childrenMap.set(fromId, new Set())
      childrenMap.get(fromId).add(toId)
      allParents.add(fromId)
      allChildren.add(toId)
      ensureId(fromId)
      ensureId(toId)
    }
    const labelRe = /^\s*(\w+)\s*\["?([^"\]]*)"?\]\s*$/
    const lm = labelRe.exec(line)
    if (lm) {
      const [, id, text] = lm
      if (text) nodeText.set(id, text)
      ensureId(id)
    }
  }

  let rootId = null
  for (const id of lineOrder) {
    if (allParents.has(id) && !allChildren.has(id)) {
      rootId = id
      break
    }
  }
  if (!rootId && lineOrder.length > 0) rootId = lineOrder[0]
  if (!rootId) return null

  const visited = new Set()
  function buildNode(id, level) {
    if (visited.has(id)) return null
    visited.add(id)
    const text = nodeText.get(id) || id
    const childIds = childrenMap.get(id)
    const children = []
    if (childIds) {
      for (const cid of childIds) {
        const child = buildNode(cid, level + 1)
        if (child) children.push(child)
      }
    }

    const result = { id, topic: text, expanded: level < 2, children }
    result.metadata = { definition: '', syntax: '', examples: [], pitfalls: [], advice: '' }

    if (level === 0) {
      result.style = { fontSize: '20', color: '#ffffff', background: '#1e40af', fontWeight: 'bold' }
    } else if (level === 1) {
      result.style = { fontSize: '15', color: '#ffffff', background: '#7c3aed', fontWeight: '600' }
      result.branchColor = '#a78bfa'
    } else {
      result.style = { fontSize: '13', color: '#1e293b', background: '#ffffff', fontWeight: '500', border: '1.5px solid #e2e8f0' }
      result.branchColor = '#cbd5e1'
    }

    return result
  }

  return buildNode(rootId, 0)
}

// ===== Markdown → MindElixir 数据转换 =====
function markdownToMindElixir(md) {
  const lines = md.split('\n').filter(l => l.trim())
  let idCounter = 0
  const root = { id: 'root', topic: '', expanded: true, children: [], metadata: { definition: '', syntax: '', examples: [], pitfalls: [], advice: '' } }
  const stack = [root]

  for (const line of lines) {
    const headingMatch = line.match(/^(#{1,6})\s+(.+)/)
    const bulletMatch = line.match(/^(\s*)[-*]\s+(.+)/)

    if (headingMatch) {
      const level = headingMatch[1].length
      const text = headingMatch[2].trim()
      const node = {
        id: `md_${idCounter++}`,
        topic: text,
        expanded: level <= 2,
        children: [],
        metadata: { definition: '', syntax: '', examples: [], pitfalls: [], advice: '' },
      }
      while (stack.length > 1 && (stack[stack.length - 1]._level || 0) >= level) stack.pop()
      node._level = level
      stack[stack.length - 1].children.push(node)
      stack.push(node)
    } else if (bulletMatch) {
      const text = bulletMatch[2].trim()
      stack[stack.length - 1].children.push({
        id: `md_${idCounter++}`,
        topic: text,
        expanded: true,
        children: [],
        metadata: { definition: '', syntax: '', examples: [], pitfalls: [], advice: '' },
      })
    }
  }

  if (!root.topic && root.children.length > 0) {
    const first = root.children[0]
    root.topic = first.topic
    root.children = [...first.children, ...root.children.slice(1)]
  }
  return root
}

// ===== 解析内容为 MindElixir 数据 =====
function parseContent() {
  if (!props.content) return null
  const type = detectContentType(props.content)
  const trimmed = props.content.trim()

  let nodeData = null
  switch (type) {
    case 'json': nodeData = jsonToMindElixir(trimmed); break
    case 'mermaid': nodeData = mermaidToMindElixir(trimmed); break
    case 'markdown': nodeData = markdownToMindElixir(trimmed); break
    default:
      try { nodeData = jsonToMindElixir(trimmed) } catch {}
      if (!nodeData) nodeData = mermaidToMindElixir(trimmed)
      if (!nodeData) nodeData = markdownToMindElixir(trimmed)
  }

  if (!nodeData) {
    renderError.value = `解析失败 (类型: ${type}, 长度: ${trimmed.length}, 开头: ${trimmed.substring(0, 50)})`
    return null
  }
  return { nodeData, direction: 1 }
}

// ===== 初始化 MindElixir =====
function initMindElixir() {
  if (!mapRef.value) return

  // 等待容器有实际尺寸后再初始化
  let retries = 0
  function tryInit() {
    if (!mapRef.value) return
    const container = mapRef.value

    if (container.offsetWidth === 0 || container.offsetHeight === 0) {
      retries++
      if (retries < 20) {
        setTimeout(tryInit, 50)
      }
      return
    }

    if (mind) {
      mind.destroy()
      mind = null
    }

    try {
      mind = new MindElixir({
        el: container,
        direction: 1,
        toolBar: true,
        keypress: false,
        editable: false,
        contextMenu: false,
        overflowHidden: false,
        allowUndo: false,
        theme: THEME,
      })
    } catch (e) {
      renderError.value = 'MindElixir 初始化失败: ' + e.message
      return
    }

    const data = parseContent()
    if (!data) {
      // parseContent 已设置 renderError
      return
    }

    try {
      const err = mind.init(data)
      if (err) {
        renderError.value = 'MindElixir init 错误: ' + String(err)
      }
    } catch (e) {
      renderError.value = '渲染失败: ' + e.message
    }

    // 监听节点点击
    selectHandler = (nodeObj) => {
      const meta = nodeObj.metadata || metadataMap.get(nodeObj.id) || null
      detailNode.value = meta ? {
        text: nodeObj.topic,
        ...meta,
      } : { text: nodeObj.topic, definition: '', syntax: '', examples: [], pitfalls: [], advice: '' }
      showDetail.value = true
      emit('select', nodeObj)
    }

    expandHandler = (nodeObj) => {}

    scaleHandler = (scale) => {
      zoomLevel.value = Math.round(scale * 100)
    }

    mind.bus.addListener('selectNewNode', selectHandler)
    mind.bus.addListener('expandNode', expandHandler)
    mind.bus.addListener('scale', scaleHandler)
  }

  nextTick(() => tryInit())
}

// ===== 关闭详情面板 =====
function closeDetail() {
  showDetail.value = false
  detailNode.value = null
  if (mind) mind.clearSelection()
}

// ===== 工具栏方法 =====
function zoomIn() {
  if (mind) mind.scale(mind.scaleVal * 1.2)
}

function zoomOut() {
  if (mind) mind.scale(mind.scaleVal / 1.2)
}

function resetView() {
  if (mind) {
    mind.toCenter()
    mind.scaleFit()
  }
}

function expandAll() {
  if (mind) {
    const data = mind.getData()
    if (data.nodeData) {
      setExpandAll(data.nodeData, true)
      mind.refresh(data)
    }
  }
}

function collapseAll() {
  if (mind) {
    const data = mind.getData()
    if (data.nodeData) {
      setExpandAll(data.nodeData, false)
      data.nodeData.expanded = true // 根节点保持展开
      mind.refresh(data)
    }
  }
}

function setExpandAll(node, expanded) {
  if (node.children && node.children.length > 0) {
    node.expanded = expanded
    node.children.forEach(c => setExpandAll(c, expanded))
  }
}

// ===== 生命周期 =====
onMounted(() => {
  if (props.content) nextTick(() => initMindElixir())
})

onBeforeUnmount(() => {
  if (mind) {
    if (selectHandler) mind.bus.removeListener('selectNewNode', selectHandler)
    if (expandHandler) mind.bus.removeListener('expandNode', expandHandler)
    if (scaleHandler) mind.bus.removeListener('scale', scaleHandler)
    mind.destroy()
    mind = null
  }
})

watch(() => props.content, () => {
  showDetail.value = false
  detailNode.value = null
  renderError.value = ''
  metadataMap.clear()
  nextTick(() => initMindElixir())
})

defineExpose({ zoomIn, zoomOut, resetView, expandAll, collapseAll })
</script>

<template>
  <div class="mm-wrapper">
    <!-- 加载动画 -->
    <div v-if="loading" class="mm-loading">
      <div class="mm-spinner"></div>
      <p>正在生成思维导图...</p>
    </div>

    <!-- 空状态 -->
    <div v-else-if="!content" class="mm-empty">
      <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="1.5">
        <path d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l5.447 2.724A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7"/>
      </svg>
      <p>输入知识点，生成思维导图</p>
    </div>

    <!-- MindElixir 画布 + 详情面板 -->
    <template v-else>
      <!-- 错误回退 -->
      <div v-if="renderError" class="mm-empty" style="color: #ef4444;">
        <p>{{ renderError }}</p>
        <p style="font-size: 12px; color: #94a3b8;">请刷新页面重试</p>
      </div>

      <template v-else>
        <div class="mm-canvas-area">
          <div ref="mapRef" class="mm-map"></div>
        </div>
      </template>

      <!-- 右侧详情面板 -->
      <Transition name="slide">
        <div v-if="showDetail && detailNode" class="mm-panel">
          <div class="mm-panel-header">
            <h3 class="mm-panel-title">{{ detailNode.text }}</h3>
            <button class="mm-panel-close" @click="closeDetail">
              <svg width="18" height="18" viewBox="0 0 18 18"><path d="M5 5l8 8M13 5l-8 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
            </button>
          </div>
          <div class="mm-panel-body">
            <div v-if="detailNode.definition" class="mm-panel-section">
              <div class="mm-panel-label">定义</div>
              <p class="mm-panel-text">{{ detailNode.definition }}</p>
            </div>
            <div v-if="detailNode.syntax" class="mm-panel-section">
              <div class="mm-panel-label">语法</div>
              <pre class="mm-panel-code">{{ detailNode.syntax }}</pre>
            </div>
            <div v-if="detailNode.examples && detailNode.examples.length > 0" class="mm-panel-section">
              <div class="mm-panel-label">示例</div>
              <pre v-for="(ex, i) in detailNode.examples" :key="i" class="mm-panel-code">{{ ex }}</pre>
            </div>
            <div v-if="detailNode.pitfalls && detailNode.pitfalls.length > 0" class="mm-panel-section">
              <div class="mm-panel-label">常见坑点</div>
              <ul class="mm-panel-list">
                <li v-for="(p, i) in detailNode.pitfalls" :key="i">{{ p }}</li>
              </ul>
            </div>
            <div v-if="detailNode.advice" class="mm-panel-section">
              <div class="mm-panel-label">学习建议</div>
              <p class="mm-panel-text mm-panel-advice">{{ detailNode.advice }}</p>
            </div>
            <div v-if="!detailNode.definition && !detailNode.syntax && (!detailNode.examples || detailNode.examples.length === 0) && (!detailNode.pitfalls || detailNode.pitfalls.length === 0) && !detailNode.advice" class="mm-panel-empty">
              该节点无详细内容
            </div>
          </div>
        </div>
      </Transition>
    </template>
  </div>
</template>

<style>
/* ===== 容器 ===== */
.mm-wrapper {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 500px;
  background: #f8fafc;
  border-radius: 16px;
  border: 1px solid #e2e8f0;
  box-sizing: border-box;
}

/* ===== 画布区域 ===== */
.mm-canvas-area {
  width: 100%;
  height: 100%;
  min-height: 500px;
}

.mm-map {
  width: 100%;
  height: 100%;
  min-height: 500px;
}

/* ===== MindElixir 主题覆盖 ===== */
.mm-map .map-container {
  background: #f8fafc !important;
}

/* ===== 右侧详情面板 ===== */
.mm-panel {
  position: absolute;
  top: 0; right: 0;
  width: 340px;
  height: 100%;
  background: #fff;
  border-left: 1px solid #e2e8f0;
  box-shadow: -4px 0 24px rgba(0,0,0,0.06);
  z-index: 500;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.mm-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid #f1f5f9;
  flex-shrink: 0;
}

.mm-panel-title {
  font-size: 16px;
  font-weight: 700;
  color: #1e293b;
  margin: 0;
}

.mm-panel-close {
  width: 28px; height: 28px;
  border: none; border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; color: #94a3b8;
  background: transparent;
  transition: all 0.15s;
}

.mm-panel-close:hover { background: #f1f5f9; color: #64748b; }

.mm-panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px;
}

.mm-panel-section { margin-bottom: 16px; }

.mm-panel-label {
  font-size: 11px;
  font-weight: 600;
  color: #7c3aed;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 6px;
}

.mm-panel-text {
  font-size: 13px;
  color: #475569;
  line-height: 1.6;
  margin: 0;
}

.mm-panel-code {
  font-size: 12px;
  color: #1e293b;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 10px 12px;
  margin: 0 0 6px 0;
  overflow-x: auto;
  font-family: 'SF Mono', 'Fira Code', monospace;
  line-height: 1.5;
  white-space: pre-wrap;
}

.mm-panel-list {
  margin: 0;
  padding: 0 0 0 16px;
  font-size: 13px;
  color: #475569;
  line-height: 1.8;
}

.mm-panel-list li { margin-bottom: 2px; }

.mm-panel-advice {
  background: linear-gradient(135deg, #eff6ff, #f0fdf4);
  border: 1px solid #dbeafe;
  border-radius: 8px;
  padding: 10px 12px;
  font-size: 13px;
  color: #1e40af;
}

.mm-panel-empty {
  text-align: center;
  color: #94a3b8;
  font-size: 13px;
  padding: 32px 0;
}

/* ===== 面板动画 ===== */
.slide-enter-active, .slide-leave-active {
  transition: transform 0.3s ease, opacity 0.3s ease;
}
.slide-enter-from, .slide-leave-to {
  transform: translateX(100%);
  opacity: 0;
}

/* ===== 加载动画 ===== */
.mm-loading {
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  height: 100%; gap: 16px;
  color: #94a3b8; font-size: 14px;
}

.mm-spinner {
  width: 36px; height: 36px;
  border: 3px solid #e2e8f0;
  border-top-color: #3b82f6;
  border-radius: 50%;
  animation: mm-spin 0.8s linear infinite;
}

@keyframes mm-spin { to { transform: rotate(360deg); } }

/* ===== 空状态 ===== */
.mm-empty {
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  height: 100%; gap: 12px;
  color: #94a3b8; font-size: 14px;
}
</style>
