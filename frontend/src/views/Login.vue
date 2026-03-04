<template>
  <v-app class="login-app">
    <!-- Animated Background -->
    <div class="login-bg">
      <div class="bg-gradient"></div>
      <div class="bg-grid"></div>
      <div class="bg-glow glow-1"></div>
      <div class="bg-glow glow-2"></div>
      <div class="bg-glow glow-3"></div>
    </div>

    <v-container class="fill-height" fluid>
      <v-row align="center" justify="center" class="fill-height">
        <!-- Left side — branding (desktop only) -->
        <v-col cols="12" md="6" class="d-none d-md-flex flex-column align-center justify-center pa-12">
          <div class="branding-content text-center" style="max-width: 480px;">
            <div class="brand-icon-wrapper mb-6 mx-auto">
              <v-icon color="white" size="40">mdi-robot-outline</v-icon>
            </div>
            <h1 class="text-h3 font-weight-bold text-white mb-4" style="letter-spacing: -0.04em; line-height: 1.1;">
              Basile IA<br>
              <span style="background: linear-gradient(135deg, #A78BFA 0%, #22D3EE 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">
                Orchestrator
              </span>
            </h1>
            <p class="text-body-1 mb-0" style="color: rgba(255,255,255,0.5); line-height: 1.7;">
              Plataforma de orquestração multi-agente com inteligência artificial avançada. 
              Gerencie seus agentes, integrações e fluxos em um único lugar.
            </p>
            
            <!-- Features -->
            <div class="d-flex flex-column ga-3 mt-8">
              <div v-for="feature in features" :key="feature.text" class="d-flex align-center" style="color: rgba(255,255,255,0.5);">
                <v-icon :icon="feature.icon" size="18" color="#A78BFA" class="mr-3"></v-icon>
                <span class="text-body-2">{{ feature.text }}</span>
              </div>
            </div>
          </div>
        </v-col>

        <!-- Right side — login form -->
        <v-col cols="12" sm="8" md="5" lg="4">
          <v-card class="login-card pa-8 pa-md-10" rounded="2xl" elevation="24">
            <!-- Mobile Logo -->
            <div class="d-flex d-md-none align-center justify-center mb-6">
              <div class="brand-icon-wrapper-sm mr-3">
                <v-icon color="white" size="22">mdi-robot-outline</v-icon>
              </div>
              <h2 class="text-h6 font-weight-bold" style="letter-spacing: -0.02em;">Basile IA</h2>
            </div>

            <div class="mb-8">
              <h2 class="text-h5 font-weight-bold mb-2" style="letter-spacing: -0.03em;">Bem-vindo de volta</h2>
              <p class="text-body-2 text-medium-emphasis mb-0">Entre com suas credenciais para continuar</p>
            </div>

            <v-form @submit.prevent="login">
              <v-text-field
                v-model="email"
                label="Email"
                placeholder="seu@email.com"
                prepend-inner-icon="mdi-email-outline"
                type="email"
                required
                class="mb-1"
                :error-messages="emailError"
              ></v-text-field>
              
              <v-text-field
                v-model="password"
                label="Senha"
                placeholder="••••••••"
                prepend-inner-icon="mdi-lock-outline"
                :type="showPassword ? 'text' : 'password'"
                :append-inner-icon="showPassword ? 'mdi-eye-outline' : 'mdi-eye-off-outline'"
                @click:append-inner="showPassword = !showPassword"
                required
                class="mb-1"
              ></v-text-field>

              <div class="d-flex align-center justify-space-between mb-6">
                <v-checkbox
                  label="Lembrar-me"
                  density="compact"
                  hide-details
                  color="primary"
                  class="text-body-2"
                ></v-checkbox>
                <a href="#" class="text-caption text-primary font-weight-medium text-decoration-none">
                  Esqueceu a senha?
                </a>
              </div>

              <v-btn
                block
                size="large"
                color="primary"
                @click="login"
                :loading="loading"
                class="login-btn mb-4"
                rounded="lg"
              >
                <span class="font-weight-bold">Entrar</span>
                <v-icon end size="18">mdi-arrow-right</v-icon>
              </v-btn>
            </v-form>

            <v-alert
              v-if="error"
              type="error"
              variant="tonal"
              class="mt-4"
              rounded="lg"
              density="compact"
            >
              {{ error }}
            </v-alert>

            <v-divider class="my-6"></v-divider>

            <p class="text-center text-caption text-medium-emphasis mb-0">
              © 2026 Basile IA Orchestrator
            </p>
          </v-card>
        </v-col>
      </v-row>
    </v-container>
  </v-app>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()
const email = ref('')
const password = ref('')
const showPassword = ref(false)
const loading = ref(false)
const error = ref('')
const emailError = ref('')

const features = [
  { icon: 'mdi-brain', text: 'Agentes IA com orquestração inteligente' },
  { icon: 'mdi-connection', text: 'Integração MCP com qualquer serviço' },
  { icon: 'mdi-shield-check-outline', text: 'Controle de acesso multi-nível' },
  { icon: 'mdi-chart-timeline-variant', text: 'Monitoramento em tempo real' },
]

const login = async () => {
  loading.value = true
  error.value = ''
  emailError.value = ''
  
  if (!email.value) {
    emailError.value = 'Email é obrigatório'
    loading.value = false
    return
  }
  
  if (email.value && password.value) {
    setTimeout(() => {
      router.push('/')
      loading.value = false
    }, 1200)
  } else {
    error.value = 'Por favor, preencha todos os campos'
    loading.value = false
  }
}
</script>

<style scoped>
.login-app {
  font-family: 'Inter', sans-serif;
  min-height: 100vh;
}

/* ── Animated Background ── */
.login-bg {
  position: fixed;
  inset: 0;
  z-index: 0;
  overflow: hidden;
}

.bg-gradient {
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, #0F172A 0%, #1a1035 40%, #0F172A 100%);
}

.bg-grid {
  position: absolute;
  inset: 0;
  background-image: 
    linear-gradient(rgba(124, 58, 237, 0.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(124, 58, 237, 0.03) 1px, transparent 1px);
  background-size: 60px 60px;
}

.bg-glow {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  animation: float-glow 8s ease-in-out infinite;
}

.glow-1 {
  width: 400px;
  height: 400px;
  background: rgba(124, 58, 237, 0.15);
  top: 10%;
  left: 20%;
  animation-delay: 0s;
}

.glow-2 {
  width: 300px;
  height: 300px;
  background: rgba(6, 182, 212, 0.1);
  bottom: 20%;
  right: 15%;
  animation-delay: -3s;
}

.glow-3 {
  width: 200px;
  height: 200px;
  background: rgba(167, 139, 250, 0.1);
  top: 50%;
  left: 60%;
  animation-delay: -5s;
}

@keyframes float-glow {
  0%, 100% { transform: translate(0, 0) scale(1); }
  33% { transform: translate(20px, -20px) scale(1.05); }
  66% { transform: translate(-15px, 15px) scale(0.95); }
}

/* ── Brand Icon ── */
.brand-icon-wrapper {
  width: 80px;
  height: 80px;
  border-radius: 24px;
  background: linear-gradient(135deg, #7C3AED 0%, #A78BFA 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 12px 40px rgba(124, 58, 237, 0.3);
  animation: float 4s ease-in-out infinite;
}

.brand-icon-wrapper-sm {
  width: 40px;
  height: 40px;
  border-radius: 12px;
  background: linear-gradient(135deg, #7C3AED 0%, #A78BFA 100%);
  display: flex;
  align-items: center;
  justify-content: center;
}

@keyframes float {
  0%, 100% { transform: translateY(0px); }
  50% { transform: translateY(-8px); }
}

/* ── Login Card ── */
.login-card {
  position: relative;
  z-index: 1;
  border: 1px solid rgba(var(--v-border-color), 0.08);
  backdrop-filter: blur(20px);
}

.login-btn {
  height: 48px !important;
  font-size: 15px;
  letter-spacing: 0.01em;
  box-shadow: 0 8px 24px rgba(124, 58, 237, 0.3);
  transition: all 0.3s ease;
}

.login-btn:hover {
  box-shadow: 0 12px 32px rgba(124, 58, 237, 0.4);
  transform: translateY(-1px);
}
</style>
