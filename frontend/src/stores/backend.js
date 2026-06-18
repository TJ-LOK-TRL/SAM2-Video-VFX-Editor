import { defineStore } from 'pinia';
import { ref } from 'vue';
import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL

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

    async function pollVideoMaskJob(jobId, { intervalMs = 2000, timeoutMs = 30 * 60 * 1000, onStatusUpdate = null } = {}) {
        const startedAt = Date.now()

        while (true) {
            const { data } = await axios.get(`${API_BASE_URL}/video/mask/status/${jobId}`)

            if (onStatusUpdate) {
                onStatusUpdate(data)
            }

            if (data.status === 'done') {
                return data
            }

            if (data.status === 'failed') {
                throw new Error(data.error || 'Falha ao gerar máscaras do vídeo')
            }

            if (Date.now() - startedAt > timeoutMs) {
                throw new Error('Tempo limite excedido a aguardar pelas máscaras')
            }

            await new Promise(resolve => setTimeout(resolve, intervalMs))
        }
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

            // Caso contrário, o backend devolveu um job_id -> fazer polling até terminar
            return await pollVideoMaskJob(response.data.job_id, {
                intervalMs: options.pollIntervalMs,
                onStatusUpdate: options.onStatusUpdate,
            });
        } catch (error) {
            console.error("Erro na requisição:", error);
            throw error;
        }
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
        getMasksForVideo, download, convertImageToVideo }
})

