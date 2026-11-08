<template>
  <header class="topbar">
    <span class="brand">Turtle</span>
    <nav>
      <RouterLink to="/">Portfolio</RouterLink>
      <RouterLink to="/transactions">Transactions</RouterLink>
      <RouterLink to="/chart">Chart</RouterLink>
      <RouterLink to="/signals">Signals</RouterLink>
    </nav>
  </header>
  <main>
    <RouterView />
  </main>
</template>
