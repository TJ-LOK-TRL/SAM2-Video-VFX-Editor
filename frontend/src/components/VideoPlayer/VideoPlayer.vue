<template>
    <div class="video-player-container" ref="videoPlayerContainer" @wheel.prevent="handleWheelZoom">
        <div class="zoom-wrapper" :style="{ transform: `scale(${videoEditorStore.zoomLevel})` }">
            <div class="video-space-container-parent" ref="spaceContainerParentRef">
                <div class="video-space-container" ref="spaceContainerRef">
                    <template v-for="element in videoEditorStore.getElements()" :key="element.id">
                        <BoxVideo v-if="element.type === 'video'" :video="element" />
                        <BoxText v-else-if="element.type === 'text'" :text-element="element" />
                    </template>

                    <AnimationLines />
                </div>
            </div>
        </div>
    </div>
</template>

<script setup>
    import { ref, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
    import { useVideoEditor } from '@/stores/videoEditor'
    import BoxVideo from './BoxVideo.vue'
    import BoxText from './BoxText.vue'
    import { getRectWithZoom } from '@/assets/js/utils.js'
    import AnimationLines from '@/components/Sidebar/Animations/AnimationVisuals/AnimationLines.vue'

    const props = defineProps({
        parentMaxHeight: Number
    })

    const videoEditorStore = useVideoEditor()

    const boxVideoRef = ref(null)
    const spaceContainerRef = ref(null)
    const spaceContainerParentRef = ref(null)
    const videoPlayerContainer = ref(null)

    let previousContainerRect = null
    let parentResizeObserver = null

    function recalculateSpaceContainerBoxSize() {
        const videoWidth = videoEditorStore.videoPlayerWidth
        const videoHeight = videoEditorStore.videoPlayerHeight
        //console.log('VideoWidth:', videoWidth)
        //console.log('VideoHeight:', videoHeight)

        const containerEl = spaceContainerRef.value
        const parentEl = spaceContainerParentRef.value

        if (!containerEl || !parentEl) {
            console.warn('VideoPlayer: refs do container ainda não estão prontos, a ignorar recálculo de tamanho')
            return
        }

        const containerWidth = parentEl.clientWidth
        const containerHeight = parentEl.clientHeight

        // Calcular aspect-ratio
        const videoRatio = videoWidth / videoHeight
        const containerRatio = containerWidth / containerHeight
        //console.log('Ratios:', videoRatio, containerRatio)

        let displayWidth
        let displayHeight

        if (containerRatio > videoRatio) {
            displayHeight = containerHeight
            displayWidth = videoRatio * displayHeight
        } else {
            displayWidth = containerWidth
            displayHeight = displayWidth / videoRatio
        }

        videoEditorStore.setVideoPlayerSize(displayWidth, displayHeight)
        spaceContainerRef.value.style.width = `${displayWidth}px`
        spaceContainerRef.value.style.height = `${displayHeight}px`

        //console.log('OldVideoSize:', videoWidth, videoHeight)
        //console.log('NewVideoSize:', videoWidth, videoHeight)
        //console.log('ContainerSize:', containerWidth, containerHeight)
        //console.log('SpaceContainerSize:', displayWidth, displayHeight)

        recalculateBoxsSize()
    }

    function recalculateBoxsSize() {
        const container = spaceContainerRef.value;

        if (!container) {
            console.error(`Container is null`);
            return;
        }

        //console.trace("Here")
        Array.from(container.children).forEach((box) => {
            //const newContainerRect = container.getBoundingClientRect();
            const newContainerRect = getRectWithZoom(container, videoEditorStore.zoomLevel)

            const originalTransform = box.style.transform;
            box.style.transform = 'none';
            const boxRect = getRectWithZoom(box, videoEditorStore.zoomLevel)

            if (!previousContainerRect) {
                previousContainerRect = newContainerRect;
                console.log('Not updated!');
                return;
            }

            const widthRatio = (newContainerRect.width) / previousContainerRect.width;
            const heightRatio = (newContainerRect.height) / previousContainerRect.height;
            //console.log('NEW:', newContainerRect)
            //console.log('OLD:', previousContainerRect)
            //console.log('widthRatio:', widthRatio);
            //console.log('heightRatio:', heightRatio);
            //console.log('zoom:', videoEditorStore.zoomLevel)

            const boxWidth = boxRect.width
            const boxHeight = boxRect.height
            //console.log('boxWidth:', boxWidth, box.style.width)
            //console.log('boxHeight:', boxHeight, box.style.height)

            // Calcula posição relativa atual (em relação ao container)
            const currentLeft = boxRect.left - newContainerRect.left;
            const currentTop = boxRect.top - newContainerRect.top;

            // Aplica as proporções
            const newBoxWidth = boxWidth * widthRatio;
            const newBoxHeight = boxHeight * heightRatio;
            const newBoxLeft = currentLeft * widthRatio;
            const newBoxTop = currentTop * heightRatio;

            box.style.width = `${newBoxWidth}px`;
            box.style.height = `${newBoxHeight}px`;
            box.style.left = `${newBoxLeft}px`;
            box.style.top = `${newBoxTop}px`;

            //console.log(box)
            //console.log(boxRect)
            //console.log(box.style.width)
            //console.log('BoxWidth:', newBoxWidth);
            //console.log('BoxHeight:', newBoxHeight);
            //console.log(newBoxLeft);
            //console.log(newBoxTop);

            box.style.transform = originalTransform;
        });

        previousContainerRect = getRectWithZoom(container, videoEditorStore.zoomLevel);
    }

    function onVideoLoaded(video) {
        if (!spaceContainerParentRef.value) {
            console.warn('VideoPlayer: instância já desmontada, a ignorar evento de vídeo carregado')
            return
        }

        previousContainerRect = null
        recalculateSpaceContainerBoxSize()

        parentResizeObserver?.disconnect()
        parentResizeObserver = new ResizeObserver(() => {
            recalculateSpaceContainerBoxSize()
        })
        parentResizeObserver.observe(spaceContainerParentRef.value)

        videoEditorStore.onAddMapBoxVideo((newVideo, boxElement) => {
            if (video.id !== newVideo.id) return
            const { width, height } = videoEditorStore.getVideoPlayerSize();
            boxElement.box.value.setSize(width, height)
        })
    }

    function handleWheelZoom(event) {
        const delta = -event.deltaY

        const zoomSpeed = 0.0015
        videoEditorStore.zoomLevel = Math.min(3, Math.max(0.2, videoEditorStore.zoomLevel + delta * zoomSpeed))
    }

    const handleFirstVideoMetadataLoaded = (video) => {
        onVideoLoaded(video)
    }

    const handleVideoMetadataLoaded = (video) => {
        if (videoEditorStore.getVideos().length > 1)
            recalculateBoxsSize()
    }

    onMounted(async () => {
        await nextTick()
        videoEditorStore.setVideoPlayerContainer(videoPlayerContainer.value)
        videoEditorStore.setVideoPlayerSpaceContainer(spaceContainerRef.value)
        videoEditorStore.onFirstVideoMetadataLoaded(handleFirstVideoMetadataLoaded)
        videoEditorStore.onVideoMetadataLoaded(handleVideoMetadataLoaded)
    })

    onBeforeUnmount(() => {
        parentResizeObserver?.disconnect()
        videoEditorStore.removeOnFirstVideoMetadataLoaded(handleFirstVideoMetadataLoaded)
        videoEditorStore.removeOnVideoMetadataLoaded(handleVideoMetadataLoaded)
    })
</script>

<style scoped>
    .video-player-container {
        display: flex;
        justify-content: center;
        align-items: center;
        width: 100%;
        height: calc(100% - 50px);
        padding: 20px;
        box-sizing: border-box;
        overflow: hidden;
    }

    .video-space-container-parent {
        position: relative;
        display: flex;
        justify-content: center;
        align-items: center;
        width: 100%;
        height: 100%;
    }

    .video-space-container {
        position: relative;
        width: 100%;
        height: 100%;
        /*max-width: 1000px;*/
        max-height: 100%;
        background-color: black;
    }

    .video-player-container.hovering-over:hover::before {
        content: '';
        position: absolute;
        top: 6px;
        left: 6px;
        right: 6px;
        bottom: 6px;
        border: 0.3px dashed var(--main-color);
        border-radius: 12px;
        pointer-events: none;
        background-color: var(--main-color-alpha);
    }

    .zoom-wrapper {
        position: absolute;
        width: 100%;
        height: 100%;
        padding: 20px;
        top: 0;
        left: 0;
        display: flex;
        justify-content: center;
        align-items: center;
    }
</style>