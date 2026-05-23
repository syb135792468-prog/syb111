<script setup>
import PathStep from './PathStep.vue'

defineProps({
  steps: { type: Array, default: () => [] },
})
</script>

<template>
  <div class="space-y-0">
    <PathStep
      v-for="(step, i) in steps"
      :key="step.order"
      :step="step"
      :is-last="i === steps.length - 1"
    />
  </div>
</template>
