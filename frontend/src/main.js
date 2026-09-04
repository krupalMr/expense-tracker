import { createApp } from 'vue'
import '@mdi/font/css/materialdesignicons.css'
import 'vuetify/styles'
import { createVuetify } from 'vuetify'
import App from './App.vue'
import './styles.css'

const vuetify = createVuetify({
  theme: {
    defaultTheme: 'pocketwise',
    themes: {
      pocketwise: {
        dark: false,
        colors: {
          primary: '#30345f',
          secondary: '#e87568',
          accent: '#d6a85f',
          background: '#f4f5fb',
          surface: '#ffffff',
          'surface-variant': '#eceef8',
        },
      },
      pocketwiseDark: {
        dark: true,
        colors: {
          primary: '#30345f',
          secondary: '#ff8d7e',
          accent: '#e5bb72',
          background: '#171a2e',
          surface: '#222642',
          'surface-variant': '#2c3151',
        },
      },
    },
  },
  defaults: {
    VBtn: { elevation: 0, rounded: 'sm' },
    VCard: { rounded: 'lg', elevation: 0 },
    VTextField: { variant: 'outlined', density: 'comfortable', hideDetails: 'auto' },
    VSelect: { variant: 'outlined', density: 'comfortable', hideDetails: 'auto' },
  },
})

createApp(App).use(vuetify).mount('#app')
