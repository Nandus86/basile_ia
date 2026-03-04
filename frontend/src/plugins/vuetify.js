/**
 * Vuetify Plugin Configuration — Premium Theme
 * Brand: Basile IA Orchestrator
 * Primary: Deep Violet #7C3AED
 */
import 'vuetify/styles'
import '@mdi/font/css/materialdesignicons.css'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'

const basileTheme = {
  dark: false,
  colors: {
    primary: '#7C3AED',
    'primary-darken-1': '#5B21B6',
    'primary-darken-2': '#4C1D95',
    'primary-lighten-1': '#A78BFA',
    secondary: '#64748B',
    'secondary-darken-1': '#475569',
    accent: '#06B6D4',
    error: '#EF4444',
    info: '#3B82F6',
    success: '#10B981',
    warning: '#F59E0B',
    background: '#F8FAFC',
    surface: '#FFFFFF',
    'surface-variant': '#F1F5F9',
    'on-primary': '#FFFFFF',
    'on-secondary': '#FFFFFF',
    'on-surface': '#1E293B',
    'on-background': '#1E293B',
  }
}

const basileDarkTheme = {
  dark: true,
  colors: {
    primary: '#9D4EDD', // Neon Purple
    'primary-darken-1': '#7B2CBF',
    'primary-darken-2': '#5A189A',
    'primary-lighten-1': '#C77DFF',
    secondary: '#8a94a6',
    'secondary-darken-1': '#5e6a82',
    accent: '#00f2fe',  // Cyan glow
    error: '#FF0055',
    info: '#00d2ff',
    success: '#00FC8B', // Neon Green
    warning: '#FFB800',
    background: '#070a13', // Deepest dark blue background
    surface: '#111625',    // Base card color (though we will use gradients mostly)
    'surface-variant': '#1a233a',
    'on-primary': '#FFFFFF',
    'on-secondary': '#FFFFFF',
    'on-surface': '#f8fafc',
    'on-background': '#f8fafc',
  }
}

export default createVuetify({
  components,
  directives,
  icons: {
    defaultSet: 'mdi'
  },
  theme: {
    defaultTheme: 'basileDarkTheme',
    themes: {
      basileTheme,
      basileDarkTheme
    }
  },
  defaults: {
    VBtn: {
      color: 'primary',
      variant: 'elevated',
      rounded: 'lg',
      style: 'text-transform: none; font-weight: 600; letter-spacing: 0.01em;'
    },
    VTextField: {
      variant: 'outlined',
      density: 'comfortable',
      color: 'primary',
      rounded: 'lg'
    },
    VTextarea: {
      variant: 'outlined',
      density: 'comfortable',
      color: 'primary',
      rounded: 'lg'
    },
    VSelect: {
      variant: 'outlined',
      density: 'comfortable',
      color: 'primary',
      rounded: 'lg'
    },
    VAutocomplete: {
      variant: 'outlined',
      density: 'comfortable',
      color: 'primary',
      rounded: 'lg'
    },
    VSwitch: {
      inset: true,
      color: 'primary'
    },
    VCard: {
      elevation: 0,
      rounded: 'xl',
      class: 'border-thin'
    },
    VDataTable: {
      hover: true
    },
    VChip: {
      rounded: 'lg'
    },
    VDialog: {
      maxWidth: 900,
      transition: 'dialog-bottom-transition'
    }
  }
})
