import Aura from '@primeuix/themes/aura'
import PrimeVue from 'primevue/config'
import { createApp } from 'vue'
import App from './App.vue'
import { router } from './router'
import { reloadOnStaleChunks } from './staleChunks'
import './style.css'

reloadOnStaleChunks(router)

createApp(App)
  .use(router)
  .use(PrimeVue, { theme: { preset: Aura, options: { darkModeSelector: 'system' } } })
  .mount('#app')
