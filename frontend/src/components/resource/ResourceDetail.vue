<script setup>
import { ref, watch, nextTick } from 'vue'
import { X } from 'lucide-vue-next'
import { renderMarkdown, highlightCodeBlocks } from '../../utils/markdown'
import MindmapViewer from '../mindmap/MindmapViewer.vue'

const props = defineProps({
  show: { type: Boolean, default: false },
  title: { type: String, default: '' },
  content: { type: String, default: '' },
  type: { type: String, default: 'doc' },
})

const emit = defineEmits(['close'])

const contentRef = ref(null)

function renderContent() {
  if (!contentRef.value || !props.content) return
  if (props.type === 'mindmap') return // handled by MindmapViewer component

  contentRef.value.innerHTML = renderMarkdown(props.content)
  nextTick(() => highlightCodeBlocks(contentRef.value))
}

watch(() => [props.show, props.content], renderContent)
</script>

<template>
  <Teleport to="body">
    <div v-if="show" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm" @click.self="emit('close')">
      <div class="bg-white rounded-2xl shadow-2xl w-full max-w-2xl mx-4 max-h-[85vh] flex flex-col">
        <div class="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h3 class="text-base font-semibold text-gray-800">{{ title }}</h3>
          <button @click="emit('close')" class="text-gray-400 hover:text-gray-600 p-1">
            <X class="w-5 h-5" />
          </button>
        </div>
        <div class="flex-1 overflow-y-auto px-6 py-4">
          <MindmapViewer v-if="type === 'mindmap'" :content="content" />
          <div v-else ref="contentRef" class="md-content"></div>
        </div>
      </div>
    </div>
  </Teleport>
</template>
