import { createRouter, createWebHistory } from 'vue-router'

// History mode works in production because SpaStaticFiles falls back to index.html.
export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: () => import('./views/PortfolioView.vue') },
    { path: '/transactions', component: () => import('./views/TransactionsView.vue') },
    { path: '/chart/:symbol?', component: () => import('./views/ChartView.vue'), props: true },
    { path: '/signals', component: () => import('./views/SignalsView.vue') },
    // SpaStaticFiles serves index.html for every unknown path, so typos and stale bookmarks land here.
    { path: '/:pathMatch(.*)*', component: () => import('./views/NotFoundView.vue') },
  ],
})
