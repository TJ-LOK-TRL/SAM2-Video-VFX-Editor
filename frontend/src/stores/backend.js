import { defineStore } from 'pinia';
import { ref } from 'vue';
import axios from 'axios';
import { io } from 'socket.io-client';
import { TOKEN_KEY } from '@/stores/authStore';

const API_BASE_URL = import.meta.env.VITE_API_URL

// API_BASE_URL pode ser relativo ("/api") ou absoluto ("https://host/api"); o
// socket.io precisa do host e do path do handshake separados (nginx encaminha
// /api/socket.io/* para o backend, que serve socket.io na raiz "/socket.io").
function getSocketConnectionParams() {
    const basePath = API_BASE_URL.replace(/\/$/, '')
    const isAbsolute = /^https?:\/\//i.test(basePath)

    if (isAbsolute) {
        const url = new URL(basePath)
        return { host: `${url.protocol}//${url.host}`, path: `${url.pathname}/socket.io` }
    }

    return { host: window.location.origin, path: `${basePath}/socket.io` }
}

export const useBackendStore = defineStore('backend', () => {
    const images = ref([])
    const error = ref(null)

    async function test() {
        try {
            console.log(`${API_BASE_URL}/test`)
            const response = await axios.get(`${API_BASE_URL}/test`)
            console.log(response.data)
        } catch (err) {
            error.value = err.message
        }
    }

    async function convertImageToVideo(file) {
        const formData = new FormData()
        formData.append('image', file)

        const response = await axios.post(`${API_BASE_URL}/convert/image-to-video`, formData, {
            headers: {
                'Content-Type': 'multipart/form-data'
            },
            responseType: 'blob'
        })
        
        return response.data;
    }

    async function getMediaBasicData(file) {
        const formData = new FormData()
        formData.append('video', file)

        const response = await axios.post(`${API_BASE_URL}/video/basic_data`, formData, {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        })

        return response.data
    }

    async function getMasksForFrame(frame) {
        const formData = new FormData()
        formData.append('frame', frame)

        const response = await axios.post(`${API_BASE_URL}/video/frame/mask`, formData, {
            headers: {
                'Content-Type': 'multipart/form-data'
            }
        })

        return response.data
    }

    // Espera que a task termine, usando WebSocket para progresso em tempo real
    // (incluindo frame a frame). O polling por HTTP fica como fallback caso o WS
    // falhe ou caia, e é sempre usado para buscar o resultado final assim que o
    // status fica "done" (o evento WS só traz o status, não as máscaras).
    function waitForVideoMaskJob(jobId, { fallbackIntervalMs = 10000, timeoutMs = 30 * 60 * 1000, onStatusUpdate = null } = {}) {
        return new Promise((resolve, reject) => {
            const startedAt = Date.now()
            let settled = false
            let fallbackTimer = null
            let socket = null

            const cleanup = () => {
                if (fallbackTimer) clearInterval(fallbackTimer)
                if (socket) socket.disconnect()
            }

            const settle = (fn, value) => {
                if (settled) return
                settled = true
                cleanup()
                fn(value)
            }

            async function fetchStatusOnce() {
                try {
                    const { data } = await axios.get(`${API_BASE_URL}/video/mask/status/${jobId}`)
                    handleStatusPayload(data)
                } catch (error) {
                    console.warn('Falha ao consultar status do job (fallback de polling):', error)
                }
            }

            function handleStatusPayload(data) {
                if (settled) return

                if (onStatusUpdate) {
                    onStatusUpdate(data)
                }

                if (data.status === 'done') {
                    settle(resolve, data)
                } else if (data.status === 'failed') {
                    settle(reject, new Error(data.error || 'Falha ao gerar máscaras do vídeo'))
                } else if (data.status === 'cancelled') {
                    const error = new Error('Geração de máscaras cancelada')
                    error.cancelled = true
                    settle(reject, error)
                } else if (Date.now() - startedAt > timeoutMs) {
                    settle(reject, new Error('Tempo limite excedido a aguardar pelas máscaras'))
                }
            }

            // Fallback: garante que o job termina mesmo que o WebSocket nunca ligue/caia
            fallbackTimer = setInterval(fetchStatusOnce, fallbackIntervalMs)

            try {
                const { host, path } = getSocketConnectionParams()
                socket = io(host, {
                    path,
                    transports: ['websocket'],
                    auth: { token: localStorage.getItem(TOKEN_KEY) },
                })

                socket.on('connect', () => socket.emit('subscribe_job', { job_id: jobId }))

                socket.on('job_progress', (data) => {
                    if (data.status === 'done') {
                        // O evento WS só confirma o fim; o resultado completo vem do endpoint HTTP
                        fetchStatusOnce()
                    } else {
                        handleStatusPayload(data)
                    }
                })

                socket.on('connect_error', (error) => {
                    console.warn('WebSocket indisponível, a depender do polling de fallback:', error)
                })
            } catch (error) {
                console.warn('Não foi possível iniciar o WebSocket, a depender do polling de fallback:', error)
            }

            // Confirma o estado atual já agora, caso o job termine antes de ligarmos o WS
            fetchStatusOnce()
        })
    }

    async function getMasksForVideo(videoFile, videoObjectsInfo, options = {}) {
        const formData = new FormData();

        if (!(videoFile instanceof File)) {
            throw new Error("O parâmetro videoFile deve ser um objeto File");
        }
        
        // Add video file and options to formData
        formData.append('video', videoFile);
        formData.append('scale_factor', (options.scale_factor || 1).toString());
        formData.append('start_frame', (options.start_frame || 0).toString());
        formData.append('end_frame', (options.end_frame || -1).toString());
        formData.append('video_objects', JSON.stringify(videoObjectsInfo));

        if (options.stage_name) {
            formData.append('stage_name', options.stage_name.toString());
        }

        try {
            console.log("Enviando requisição com:", {
                video: videoFile.name,
                video_objects: videoObjectsInfo,
                scale: (options.scale_factor || 1),
                start_frame: (options.start_frame || 0),
                end_frame: (options.end_frame || -1),
                stage_name: (options.stage_name || null),
            });
            // Send the request to the backend
            const response = await axios.post(`${API_BASE_URL}/video/mask`, formData, {
                headers: {
                    'Content-Type': 'multipart/form-data'
                },
            });

            // Resultado já estava cacheado (mesmo stage_name) -> vem pronto de imediato
            if (response.data.status === 'done') {
                return response.data;
            }

            // Caso contrário, o backend devolveu um job_id -> esperar pelo resultado (WS + fallback de polling)
            if (options.onJobStarted) {
                options.onJobStarted(response.data.job_id)
            }

            return await waitForVideoMaskJob(response.data.job_id, {
                fallbackIntervalMs: options.fallbackIntervalMs,
                onStatusUpdate: options.onStatusUpdate,
            });
        } catch (error) {
            console.error("Erro na requisição:", error);
            throw error;
        }
    }

    async function cancelVideoMaskJob(jobId) {
        await axios.post(`${API_BASE_URL}/video/mask/${jobId}/cancel`)
    }

    async function download(video_files, metadata) {
        try {
            const formData = new FormData();
            // 1. Adiciona os vídeos como arquivos separados
            video_files.forEach(file => {
                formData.append('videos[]', file);
            });
            // 2. Adiciona todos os metadados em um único JSON
            formData.append('metadata', JSON.stringify(metadata));
            const response = await axios.post(`${API_BASE_URL}/download`, formData, {
                headers: {
                    'Content-Type': 'multipart/form-data'
                },
                responseType: 'blob'
            });
            return response.data;
        } catch (error) {
            console.error('Erro no download:', error);
            throw error;
        }
    }

    return { test, images, error, getMediaBasicData, getMasksForFrame,
        getMasksForVideo, cancelVideoMaskJob, download, convertImageToVideo }
})

