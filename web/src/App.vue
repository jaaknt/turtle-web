<script setup lang="ts">
// Both set by vite.config.ts; releaseUrl is '' unless release.yml built this.
const version = __APP_VERSION__
const releaseUrl = __APP_RELEASE_URL__
</script>

<template>
  <header class="topbar">
    <span class="brand">Turtle</span>
    <nav>
      <RouterLink to="/">Portfolio</RouterLink>
      <RouterLink to="/analytics">Analytics</RouterLink>
      <RouterLink to="/transactions">Transactions</RouterLink>
      <RouterLink to="/chart">Chart</RouterLink>
      <RouterLink to="/signals">Signals</RouterLink>
    </nav>
    <a v-if="releaseUrl" class="version" :href="releaseUrl" target="_blank" rel="noopener" title="Release notes">{{ version }}</a>
    <span v-else class="version" title="Not a release build">{{ version }}</span>
  </header>
  <main>
    <RouterView />
  </main>
</template>
