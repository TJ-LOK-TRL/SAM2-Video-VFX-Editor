<template>
    <div class="header-container">
        <div class="project-container-left">

            <!-- Nome do Projeto -->
            <div class="project-name-container">
                <div v-if="!isEditing" class="project-name-display" @click="startEditing">
                    <span>{{ projectName }}</span>
                    <i class="fas fa-edit edit-icon"></i>
                </div>
                <input v-else v-model="projectName" @blur="stopEditing" @keydown.enter="stopEditing" ref="inputProjectName"
                    class="project-name-input" />
            </div>

            <!-- Botões de Ação -->
            <div class="save-button-container">
                <button class="action-button save-button" @click="saveProject">
                    <i class="fas fa-save"></i> Guardar
                </button>
            </div>
            <div class="undo-redo-container">
                <button @click="undoAction" class="ur-button undo-button" :disabled="!canUndo">
                    <i class="fas fa-undo"></i>
                </button>
                <button @click="redoAction" class="ur-button redo-button" :disabled="!canRedo">
                    <i class="fas fa-redo"></i>
                </button>
            </div>
        
        </div>

        <div class="actions-container">
            <button class="download-button" @click="download">
                <i class="fas fa-download"></i> Download
            </button>
        </div>
    </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'
import { useVideoEditor } from '@/stores/videoEditor'
import { useAuthStore } from '@/stores/authStore'

const videoEditor = useVideoEditor()
const authStore = useAuthStore()
const projectName = ref("Project Name")
const isEditing = ref(false)
const canUndo = ref(false)
const canRedo = ref(false)
const inputProjectName = ref(null)

function undoAction() {
    console.log('Undo clicked')
}

function redoAction() {
    console.log('Redo clicked')
}

function startEditing() {
    isEditing.value = true
    nextTick(() => inputProjectName.value.focus())
}

function stopEditing() {
    isEditing.value = false
}

async function download() {
    console.log('Download clicked')
    const data = await videoEditor.compileVideos(videoEditor.getElements(), true)
    if (data) {
        videoEditor.download(data)
    }
}

async function saveProject() {
    const success = await authStore.saveProject(projectName.value)
    if (success) {
        alert('Projeto Guardado! :) ')
    } else {
        alert('Erro ao guardar o projeto! :(')
    }
}

</script>

<style scoped>

.header-container {
    display: flex;
    justify-content: space-between;
    width: 100%;
    height: 50px;
    padding: 20px;
    align-items: center;
    /* border-bottom: 1px solid #e0e0e0; */
}

.save-button {
    background-color: #2196f3;
    color: #f5f7fa;
    border: none;
    padding: 5px 10px;
    font-size: 14px;
    border-radius: 5px;
    cursor: pointer;
    transition: background 0.2s, box-shadow 0.2s;
    display: flex;
    align-items: center;
    gap: 5px;
    box-shadow: 0 1px 3px rgba(33, 150, 243, 0.08);
}

.save-button:hover {
    background-color: #1565c0;
    color: #fff;
}

.save-button:active {
    background-color: #1976d2;
}

.save-button:disabled {
    background-color: #b0bec5;
    color: #eceff1;
    cursor: not-allowed;
}

.project-container-left {
    display: flex;
    gap: 30px;
    max-width: 50%;
}

.undo-redo-container {
    display: flex;
    gap: 10px;
}

.ur-button {
    border: none;
    font-size: 15px;
}

.project-name-container {
    display: flex;
    align-items: center;
}

.project-name-display {
    display: flex;
    align-items: center;
    gap: 8px;
    cursor: pointer;
    font-size: 17px;
    font-weight: 500;
    color: #333;
}

.edit-icon {
    font-size: 14px;
    color: #666;
}

.project-name-input {
    all: unset;
    font-size: 17px;
    font-weight: 500;
    padding: 4px 8px;
    border: 1px solid #ccc;
    border-radius: 4px;
    width: 200px;
}

.actions-container {
    display: flex;
    justify-content: flex-end;
    gap: 20px;
    max-width: 50%;
}

.download-button {
    background-color: #007bff;
    color: white;
    border: none;
    padding: 8px 14px;
    font-size: 16px;
    border-radius: 6px;
    cursor: pointer;
    transition: background 0.2s ease;
    display: flex;
    align-items: center;
    gap: 6px;
}

.download-button:hover {
    background-color: #0056b3;
}
</style>