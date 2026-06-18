<template>
  <div class="auth-container">
    <h2>Registar Conta</h2>
    <form @submit.prevent="submitRegister">
      <input v-model="email" placeholder="Email" type="email" required />
      <input v-model="password" placeholder="Password" type="password" required />
      <button :disabled="loading" type="submit">
        {{ loading ? 'A processar…' : 'Criar Conta' }}
      </button>
      <p v-if="error" class="error">{{ error }}</p>
    </form>
    <p class="switch">
      Já tem conta?
      <router-link to="/login">Faça login aqui</router-link>
    </p>
  </div>
</template>
<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/authStore.js'
const email = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')
const authStore = useAuthStore()
const router = useRouter()

async function submitRegister() {
  loading.value = true
  error.value = ''
  if (await authStore.register(email.value, password.value)) {
    router.push('/')    // após criar, vai para home (edição vídeo)
  } else {
    error.value = 'Não foi possível criar a conta. Verifica se o email já existe.'
  }
  loading.value = false
}
</script>

<style scoped>
/* reutiliza os mesmos estilos de LoginPage.vue */
.auth-container {
  max-width: 360px;
  margin: 5% auto;
  padding: 2rem;
  border: 1px solid #ddd;
  border-radius: 8px;
  background: white;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

h2 {
  text-align: center;
  margin-bottom: 1.5rem;
  color: #333;
}

input {
  width: 100%;
  padding: 0.6rem;
  margin-bottom: 1rem;
  border: 1px solid #bbb;
  border-radius: 4px;
}

button {
  width: 100%;
  padding: 0.6rem;
  border: none;
  background: #1a73e8;
  color: white;
  font-weight: bold;
  border-radius: 4px;
  cursor: pointer;
}

button:disabled {
  background: #aac3f5;
}

.error {
  color: #d32f2f;
  margin-top: 0.5rem;
  text-align: center;
}

.switch {
  text-align: center;
  margin-top: 1rem;
}

.switch a {
  color: #1a73e8;
}
</style>
