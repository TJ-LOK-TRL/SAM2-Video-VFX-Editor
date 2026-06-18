<template>
    <main class="main-container" ref="mainContainerRef">
        <LoadingSpinner :isLoading="videoEditor.isLoading" :statusText="videoEditor.loadingStatusText" />
        <PromptElementSelector />
        <ToolBar class="toolbar" />
        <div ref="mainContainerLeftRef" class="main-container-left">
            <div class="sidebar-editor-container" :ref="sidebarEditorContainer"
                :style="{ maxHeight: videoHeight + '%' }">

                <Sidebar class="sidebar" />
                
                <div ref="mainContentRef" class="main-content">

                    <div class="video-header-container">
                        <VideoHeader class="video-header" />
                        <VideoPlayer class="video-player" :parentMaxHeight="videoHeight" />
                    </div>
                </div>
            </div>
            <Timeline :parent="mainContainerLeftRef" class="timeline" @resized="setVideoPlayerHeight" />
            <!-- v-if="isVideoReady" -->
        </div>
    </main>
</template>

<script setup>
    import { useAuthStore } from '@/stores/authStore.js'
    import { ref, watch } from 'vue'
    import Sidebar from '@/components/Sidebar/Sidebar.vue'
    import VideoPlayer from '@/components/VideoPlayer/VideoPlayer.vue'
    import VideoHeader from '@/components/VideoHeader.vue'
    import Timeline from '@/components/Timeline/Timeline.vue'
    import ToolBar from '@/components/ToolBar.vue'
    import LoadingSpinner from '@/components/LoadingSpinner.vue'
    import PromptElementSelector from '@/components/Sidebar/MediaElements/PromptElementSelector.vue'
    import { useVideoEditor } from '@/stores/videoEditor'
    import { useBackendStore } from '@/stores/backend'
    import { onMounted } from 'vue'

    // Testar conexão com o backend
    const backend = useBackendStore()
    backend.test()

    // Testar autenticação
    const authStore = useAuthStore()

    const videoEditor = useVideoEditor()

    const videoHeight = ref(70)
    const mainContainerRef = ref(null)
    const mainContentRef = ref(null)
    const mainContainerLeftRef = ref(null)
    const sidebarEditorContainer = ref(null)

    watch(() => videoEditor.maskHandler.selectMaskType, (newValue) => {
        if (newValue) {
            mainContainerRef.value.style.cursor = 'crosshair'
        } else {
            mainContainerRef.value.style.cursor = 'default'
        }
    })

    function setVideoPlayerHeight(newTimeLineHeight) {
        videoHeight.value = (100 - newTimeLineHeight)
    }

    onMounted(() => {
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Delete') {
                videoEditor.removeElement(videoEditor.selectedElement)
            }
        })

        window.getVideos = () => videoEditor.getVideos();
    })
</script>

<style scoped>
    .main-container {
        position: relative;
        display: flex;
        width: 100%;
        height: 100%;
        background-color: #eff0f2;
        overflow: hidden;
    }

    .main-container-left {
        position: relative;
        display: flex;
        flex-direction: column;
        width: 100%;
        height: 100%;
        flex: 1;
        min-width: 0;
        /* <- ESSENCIAL WTFF */
    }

    .sidebar-editor-container {
        display: flex;
        width: 100%;
        height: 100%;
    }

    .main-content {
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        gap: 20px;
        width: 100%;
        height: 100%;
        min-width: 0;
    }

    .video-player {
        position: relative;
        width: 100%;
    }

    .video-header-container {
        position: relative;
        width: 100%;
        height: 100%;
    }
</style>