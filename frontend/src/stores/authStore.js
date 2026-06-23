import { defineStore } from 'pinia'
import { useVideoEditor } from '@/stores/videoEditor'
import { useBackendStore } from '@/stores/backend'
import router from '@/router'
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL
export const TOKEN_KEY = 'auth_token'
const USER_KEY = 'currentUser'

function setAuthHeader(token) {
  if (token) {
    axios.defaults.headers.common['Authorization'] = `Bearer ${token}`
  } else {
    delete axios.defaults.headers.common['Authorization']
  }
}

// Se o token expirar/for inválido a meio de uma sessão, qualquer pedido falha com 401 -> forçar logout e voltar ao login
axios.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      useAuthStore().logout()
      if (router.currentRoute.value.name !== 'login') {
        router.push('/login')
      }
    }
    return Promise.reject(error)
  }
)

export const useAuthStore = defineStore('auth', {
  state: () => {
    const savedToken = localStorage.getItem(TOKEN_KEY) || null
    const savedCurrentUser = JSON.parse(localStorage.getItem(USER_KEY) || 'null')

    setAuthHeader(savedToken)

    return {
      token: savedToken,
      currentUser: savedCurrentUser
    }
  },
  getters: {
    isLoggedIn: (state) => !!state.token,
    getUsername: (state) => state.currentUser?.username || '',
    getProjects: (state) => state.currentUser?.projects || []
  },
  actions: {
    _setSession(token, email) {
      this.token = token
      this.currentUser = { email, username: email.split('@')[0], projects: this.currentUser?.projects || [] }
      setAuthHeader(token)
      localStorage.setItem(TOKEN_KEY, token)
      localStorage.setItem(USER_KEY, JSON.stringify(this.currentUser))
    },
    async login(email, password) {
      try {
        const response = await axios.post(`${API_BASE_URL}/auth/login`, { email, password })
        this._setSession(response.data.access_token, response.data.email)
        return true
      } catch (error) {
        console.error('Erro ao iniciar sessão:', error)
        return false
      }
    },
    async register(email, password) {
      try {
        const response = await axios.post(`${API_BASE_URL}/auth/register`, { email, password })
        this._setSession(response.data.access_token, response.data.email)
        return true
      } catch (error) {
        console.error('Erro ao registar:', error)
        return false
      }
    },
    // Restaura a sessão a partir do token guardado (ex.: ao recarregar a página), validando-o no backend.
    async restoreSession() {
      if (!this.token) return false

      try {
        await axios.get(`${API_BASE_URL}/auth/me`)
        return true
      } catch (error) {
        console.warn('Sessão inválida ou expirada, a fazer logout:', error)
        this.logout()
        return false
      }
    },
    logout() {
      this.token = null
      this.currentUser = null
      setAuthHeader(null)
      localStorage.removeItem(TOKEN_KEY)
      localStorage.removeItem(USER_KEY)
    },
    addProject(project) {
      if (this.currentUser) {
        this.currentUser.projects.push(project)
        this._saveCurrentUser()
      }
    },
    _saveCurrentUser() {
      if (this.currentUser) {
        localStorage.setItem(USER_KEY, JSON.stringify(this.currentUser))
      }
    },
    async _generateThumbnail() {
      try {
        const videoEditor = useVideoEditor()
        const videos = videoEditor.getVideos()
        if (videos.length === 0) return null
        return 'thumbail-placeholder'
      } catch (error) {
        console.error('Error generating thumbnail:', error)
        return null
      }
    },
    async saveProject(projectName) {
      if (!this.currentUser) return false
      const videoEditor = useVideoEditor()
      const projectData = videoEditor.exportProject()
      const thumbnail = await this._generateThumbnail()

      const newProject = {
        name: projectName,
        data: JSON.stringify(projectData), // dados do projeto
        thumbnail // miniatura do projeto
      }
      try{
        const response = await axios.post(`${API_BASE_URL}/projects`, newProject)
        const savedProject = response.data
        this.currentUser.projects.push(savedProject) // adiciona o projeto ao user atual
        this._saveCurrentUser() // guarda no LocalStorage
        return savedProject
      } catch (error) {
        console.error('Error saving project:', error)
        return null
      }
    },
    async loadProject(projectId) {
      const project = this.currentUser.projects.find(p => p.id === projectId)
      if (!project) {
        console.error('Project not found:', projectId)
        return null
      }

      const videoEditor = useVideoEditor()
      const success = await videoEditor.importProject(project.data)
      return success
    },


    async deleteProject(projectId) {
      if (!this.currentUser) return false

      // remove o projeto pelo Id
      this.currentUser.projects = this.currentUser.projects.filter(p => p.id !== projectId)
      this._saveCurrentUser() // guarda no LocalStorage
      return true
    },

    async fetchProjectById(projectId) {
      try {
        const backend = useBackendStore()
        const response = await backend.get(`/projects/${projectId}`)
            return response.data
      } catch(error) {
        console.error('Error fetching project by ID:', error)
        return null
      }
    }
  }
})
