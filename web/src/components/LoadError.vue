<script setup lang="ts">
defineProps<{
  what: string // what failed to load, as a phrase: 'the portfolio', 'the signals'
  error: string
}>()
defineEmits<{ retry: [] }>()
</script>

<template>
  <!-- A .controls bar, so the button looks like every other control. -->
  <div class="controls" role="alert">
    <p class="error">Couldn't load {{ what }}: {{ error }}</p>
    <button type="button" @click="$emit('retry')">Try again</button>
  </div>
</template>

<style scoped>
.controls {
  gap: 0.5rem 1rem;
}
.controls p {
  margin: 0;
}
</style>
