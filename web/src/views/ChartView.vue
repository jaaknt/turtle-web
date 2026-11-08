<script setup lang="ts">
defineProps<{ symbol?: string }>()
</script>

<template>
  <h1>Chart{{ symbol ? ` — ${symbol}` : '' }}</h1>
  <p class="placeholder">Built in Step 9.</p>
</template>
