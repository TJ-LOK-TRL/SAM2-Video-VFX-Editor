<template>
    <ResizableBox ref="boxVideoRef" class="video-box" :enable-resize="enableResize" @click="handleClick"
        :class="{ 'no-pointer-events': !video?.shouldBeDraw || !video?.visible, 
        'element-box-selected': video?.id === videoEditor?.selectedElement?.id && video?.visible && video?.shouldBeDraw}">
        <!-- <video></video> -->
        <canvas ref="videoCanvasRef" class="video-canvas"></canvas>

        <!-- Canvas para detectar pixels da máscara -->
        <canvas ref="maskCanvasRef" class="mask-canvas"></canvas>

        <!-- Canvas para desenhar a máscara ativa com cor -->
        <canvas ref="activeMaskCanvasRef" class="active-mask-canvas"></canvas>

        <!-- Canvas para desenhar efeitos de cores -->
        <canvas ref="colorEffectCanvasRef" class="color-effect-canvas"></canvas>

        <!-- Mostrar os pontos -->
        <div v-for="(point, index) in video?.points" :key="index"
            v-show="point.show && videoEditor.maskHandler.selectedMaskObjectId == point.objId"
            :style="{ top: (100 * point.y / point.height) + '%',  left: (100 * point.x / point.width) + '%' }"
            :class="{ point: true, add: point.type === 'add', remove: point.type === 'remove' }">
            <i v-if="point.type == 'add'" class="fas fa-plus"></i>
            <i v-else-if="point.type == 'remove'" class="fas fa-minus"></i>
        </div>

        <!-- Container das máscaras -->
        <div class="masks-container" ref="maskContainerRef" v-if="video && video.masks.length"
            @mousemove="checkMaskHover($event)" @click="checkMaskClick($event)" @mouseleave="onHoverLeave($event)">
            <img v-for="mask in video.masks" :key="mask.id" :src="mask.url" class="mask-image" />
        </div>
    </ResizableBox>
</template>

<script setup>
    import { ref, onMounted, defineExpose, watch, nextTick, onBeforeUnmount, onUnmounted, computed } from 'vue';
    import ResizableBox from '@/components/ResizableBox.vue';
    import { useVideoEditor } from '@/stores/videoEditor';
    import { useTimelineStore } from '@/stores/timeline'
    import { hexToRgb, getRectWithZoom, generateUUID } from '@/assets/js/utils.js';

    const videoEditor = useVideoEditor()
    const timelineStore = useTimelineStore()

    const props = defineProps({
        video: Object
    });

    const video = ref(null)
    const enableResize = ref(false)
    const boxVideoRef = ref(null)
    const activeMaskCanvasRef = ref(null);
    const maskContainerRef = ref(null);
    const maskCanvasRef = ref(null);
    const colorEffectCanvasRef = ref(null);
    const videoCanvasRef = ref(null);
    const shouldUpdateVideoMasks = ref(false);
    const isBoundingMaskActive = computed(() => {
        return videoEditor.selectedToolIcon === 'sam' && videoEditor.effectHandler.originalVideo?.samState === 'SamEffects'
    });
    const onDrawVideoCallbacks = ref(new Map())
    const drawVideoCallbacksCache = ref({});

    const lastDrawFrame = ref(-1)
    const preprocessedMasks = ref({})
    let maskAnimationFrameId = null
    let videoAnimationFrameId = null

    watch(
        [() => videoEditor.maskHandler.selectMaskType, () => videoEditor.selectedTool, () => videoEditor.selectedToolIcon],
        ([maskType, tool]) => {
            //shouldUpdateVideoMasks.value = tool === 'configSam' || tool === 'samEffects' || tool === 'colorEffect' || tool === 'overlayEffect' || tool === 'blendEffect'
            console.log('AQUI:', videoEditor.effectHandler.originalVideo?.samState)
            shouldUpdateVideoMasks.value = tool === 'sam' && videoEditor.effectHandler.originalVideo?.samState === 'ConfigSam'
            if (videoEditor.maskHandler?.video?.id === video?.value?.id) {
                //enableResize.value = !maskType && tool !== 'samEffects' && tool !== 'colorEffect' && tool !== 'overlayEffect' && tool !== 'blendEffect'
                enableResize.value = !maskType
            }
            else {
                enableResize.value = true
            }
        }
    )

    watch(isBoundingMaskActive, async () => {
        videoEditor.maskHandler.clearCanvas(activeMaskCanvasRef.value, ...getBoxVideoSize())
        if (isBoundingMaskActive.value) {
            await videoEditor.maskHandler.drawVisibleMasks(activeMaskCanvasRef.value, video.value.masks, ...getBoxVideoSize());
        }

        if (shouldUpdateVideoMasks.value) {
            updateVideoMasks()
        }
    })

    //watch(() => video.value?.color, (newColor) => {
    //    if (!newColor || !video.value?.trackMasks) return;
    //
    //    videoEditor.isLoading = true;
    //
    //    const rgb = hexToRgb(newColor);
    //    if (!rgb) {
    //        videoEditor.isLoading = false;
    //        return;
    //    }
    //
    //    const maskColor = [rgb.r, rgb.g, rgb.b, 100];
    //
    //    const processingPromises = [];
    //
    //    for (const frameIdx of Object.keys(video.value.trackMasks)) {
    //        const frameData = video.value.trackMasks[frameIdx];
    //
    //        for (const objId of Object.keys(frameData)) {
    //            const maskData = frameData[objId];
    //            processingPromises.push(
    //                videoEditor.maskHandler.preprocessImage(
    //                    maskData,
    //                    maskColor,
    //                    { width: 0, color: [rgb.r, rgb.g, rgb.b, 255] }
    //                ).then(processedImage => {
    //                    preprocessedMasks.value[frameIdx][objId] = processedImage;
    //                })
    //            );
    //        }
    //    }
    //
    //    Promise.all(processingPromises)
    //        .then(() => {
    //            lastDrawFrame.value = -1;
    //            return updateVideoMasks();
    //        })
    //        .then(() => {
    //            videoEditor.isLoading = false;
    //        })
    //        .catch(error => {
    //            console.error("Error processing masks:", error);
    //            videoEditor.isLoading = false;
    //        });
    //}, { immediate: true });

    watch(() => video.value?.trackMasks, async () => {
        if (!video.value?.trackMasks || Object.keys(video.value.trackMasks).length === 0) {
            videoEditor.maskHandler.clearCanvas(activeMaskCanvasRef.value, ...getBoxVideoSize())
            return;
        }

        //videoEditor.isLoading = true;
        preprocessedMasks.value = {};

        for (const frameIdx of Object.keys(video.value.trackMasks)) {
            const frameData = video.value.trackMasks[frameIdx];
            if (!preprocessedMasks.value[frameIdx]) {
                preprocessedMasks.value[frameIdx] = {};
            }

            for (const objId of Object.keys(frameData)) {
                const maskData = frameData[objId];
                preprocessedMasks.value[frameIdx][objId] = await videoEditor.maskHandler.preprocessImage(maskData, [0, 255, 0, 100]);
            }
        }

        lastDrawFrame.value = -1;
        await updateVideoMasks();
        videoEditor.isLoading = false;
    }, { deep: true });

    async function updateVideoMasks() {
        if (shouldUpdateVideoMasks.value == false) return

        const currentFrame = video.value.frameIdx
        if (currentFrame in video.value.trackMasks) {
            if (lastDrawFrame.value != currentFrame) {
                lastDrawFrame.value = currentFrame
                const currentFrameMasks = preprocessedMasks.value[currentFrame];

                const canvas = activeMaskCanvasRef.value
                const [width, height] = getBoxVideoSize()
                canvas.width = width
                canvas.height = height

                const tempCanvas = document.createElement('canvas');
                tempCanvas.width = canvas.width;
                tempCanvas.height = canvas.height;
                const tempCtx = tempCanvas.getContext('2d');

                for (const objId of Object.keys(currentFrameMasks)) {
                    const image = currentFrameMasks[objId]
                    tempCtx.drawImage(image, 0, 0, canvas.width, canvas.height);
                }

                await videoEditor.maskHandler.drawImage(canvas, tempCanvas)
            }
        } else {
            if (lastDrawFrame.value != -1) {
                lastDrawFrame.value = -1
                videoEditor.maskHandler.clearCanvas(activeMaskCanvasRef.value, ...getBoxVideoSize())
            }
        }
    }

    async function updateVideoMasksSmooth() {
        updateVideoMasks()
        maskAnimationFrameId = requestAnimationFrame(updateVideoMasksSmooth)
    }

    function handleClick(event) {
        if (videoEditor.maskHandler.selectMaskType) {
            const objId = videoEditor.maskHandler.selectedMaskObjectId;
            if (objId == null) return;
            if (!video.value) return;
            if (videoEditor.maskHandler.video?.id != video.value.id) return;

            const type = videoEditor.maskHandler.selectMaskType;
            const canvas = maskCanvasRef.value;
            const rect = canvas.getBoundingClientRect();
            const zoom = videoEditor.zoomLevel;
            const x = (event.clientX - rect.left) / zoom;
            const y = (event.clientY - rect.top) / zoom;
            const realX = ((event.clientX - rect.left) / rect.width) * video.value.width;
            const realY = ((event.clientY - rect.top) / rect.height) * video.value.height;
            const width = rect.width / zoom;
            const height = rect.height / zoom;
            const id = generateUUID();
            console.log('X:', x)
            console.log('Y:', y)
            console.log('Width:', rect.width)
            console.log('Height:', rect.height)
            console.log('RealX:', realX)
            console.log('RealY:', realY)
            console.log('rect.width =', rect.width)
            console.log('rect.height =', rect.height)
            console.log('video.value.width =', video.value.width)
            console.log('video.value.height =', video.value.height)
            console.log('x% =', (100 * x / width) + '%')
            console.log('y% =', (100 * y / height) + '%')
            console.log('id =', id)
            const show = true;
            const clickRadius = 10;

            const pointIndex = video.value.points.findIndex(point => {
                if (point.objId !== objId) return false;
                const dx = point.x - x;
                const dy = point.y - y;
                return Math.sqrt(dx * dx + dy * dy) <= clickRadius;
            });

            if (pointIndex !== -1) {
                video.value.points.splice(pointIndex, 1);
            } else {
                video.value.points.push({ x, y, realX, realY, width, height, type, show, objId, id });
                console.log("Ponto adicionado:", { x, y, realX, realY, width, height, type, show, objId, id });
            }
        }

        videoEditor.selectEditorElement(video.value)
    }

    function getBoxVideoSize() {
        try {
            const box = boxVideoRef.value?.boxRef
            if (!box) {
                console.warn('boxRef está nulo, veja seu id abaixo:')
                console.log('Video Id:', video.value.id)
                return [0, 0]
            }

            const rect = boxVideoRef.value.getRect()

            return [
                rect.width,
                rect.height
            ]
        } catch (e) {
            console.error('Erro ao tentar acessar boxRef:', e)
            console.trace()
            return [0, 0]
        }
    }

    function checkMaskHover(event) {
        if (!isBoundingMaskActive.value) return

        boxVideoRef.value.pauseTransform()
        const detected = videoEditor.maskHandler.maskEvent(event, maskCanvasRef.value, video.value.masks,
            boxVideoRef.value.getRotation(),
            boxVideoRef.value.getFlip(),
            videoEditor.zoomLevel,
            colorEffectCanvasRef.value,
            mask => {
                if (videoEditor.maskHandler.activeMask?.id == mask.id || videoEditor.maskHandler.selectedMask?.id == mask.id)
                    return

                videoEditor.maskHandler.activeMask = mask;
                videoEditor.maskHandler.drawVisibleMasks(activeMaskCanvasRef.value, video.value.masks, ...getBoxVideoSize())
            },
            mask => {
                if (videoEditor.maskHandler.activeMask?.id == mask.id) {
                    videoEditor.maskHandler.activeMask = null;
                    videoEditor.maskHandler.drawVisibleMasks(activeMaskCanvasRef.value, video.value.masks, ...getBoxVideoSize())
                }
            }
        )
        boxVideoRef.value.restoreTransform()

        if (detected) {
            enableResize.value = false
        } else {
            enableResize.value = true
        }
    }

    function checkMaskClick(event) {
        if (!isBoundingMaskActive.value) return

        boxVideoRef.value.pauseTransform()
        const detected = videoEditor.maskHandler.maskEvent(event, maskCanvasRef.value, video.value.masks,
            boxVideoRef.value.getRotation(),
            boxVideoRef.value.getFlip(),
            videoEditor.zoomLevel,
            colorEffectCanvasRef.value,
            mask => {
                if (videoEditor.maskHandler.selectedMask?.id == mask.id) {
                    videoEditor.maskHandler.selectedMask = null;
                    videoEditor.maskHandler.setMaskToEdit(videoEditor.maskHandler.selectedMask)
                    videoEditor.maskHandler.drawVisibleMasks(activeMaskCanvasRef.value, video.value.masks, ...getBoxVideoSize())
                    return
                }

                videoEditor.maskHandler.selectedMask = mask;
                videoEditor.maskHandler.setMaskToEdit(videoEditor.maskHandler.selectedMask)
                videoEditor.maskHandler.drawVisibleMasks(activeMaskCanvasRef.value, video.value.masks, ...getBoxVideoSize())
            },
            mask => {

            }
        )
        boxVideoRef.value.restoreTransform()

        if (detected) {
            enableResize.value = false
        } else {
            enableResize.value = true
        }
    }

    function onHoverLeave(event) {
        if (!isBoundingMaskActive.value) return

        if (videoEditor.maskHandler.activeMaskId != null) {
            videoEditor.maskHandler.activeMaskId = null
            videoEditor.maskHandler.drawVisibleMasks(activeMaskCanvasRef.value, video.value.masks, ...getBoxVideoSize())
        }
    }

    async function drawVideo() {
        if (!video.value.shouldBeDraw) return
        if (!video.value.visible) return

        const frame_idx = video.value.frameIdx

        let useCache = true
        let img = video.value.element
        img = await handleChromaKey(img, video.value.chromaKeyDetectionData)
        for (const [id, callbackData] of onDrawVideoCallbacks.value.entries()) {
            //console.log('CALLING CALLBACK', id, callbackData)
            const { callback, allow_cache } = callbackData
            if (!useCache || !allow_cache) {
                img = await callback(img);
                continue
            }

            if (!drawVideoCallbacksCache.value[id]) {
                drawVideoCallbacksCache.value[id] = new Map();
            }

            const cache = drawVideoCallbacksCache.value[id];
            if (cache.has(frame_idx)) {
                img = cache.get(frame_idx);
            } else {
                console.log('Calling callback:', id, frame_idx);
                const result = await callback(img);
                if (!result) return;
                cache.set(frame_idx, result);
                img = result;
            }
        }
        videoEditor.maskHandler.drawVideoFrame(videoCanvasRef.value, img, ...getBoxVideoSize())
    }

    async function updateVideoSmooth() {
        await drawVideo()
        videoAnimationFrameId = requestAnimationFrame(updateVideoSmooth)
    }

    async function handleChromaKey(img, newData) {
        if (!newData || !img) {
            return img
        }

        drawVideoCallbacksCache.value = {}

        await video.value.waitUntilVideoIsReady()

        let color;
        if (newData.detectionType === 'Color') {
            color = hexToRgb(newData.selectedColor);
        }
        else if (newData.detectionType === 'Position') {
            const [x, y] = newData.position
            color = video.value.getPixelColor(x, y);
        }
        else {
            console.warn('Tipo de detecção desconhecido:', newData.detectionType);
            return;
        }

        //console.log('Color:', color, 'tolerance:', newData.tolerance)
        const [width, height] = getBoxVideoSize()
        const outputCanvas = document.createElement('canvas')
        videoEditor.maskHandler.applyChromaKeyOnCanvas(img, outputCanvas, color, newData.tolerance, width, height);

        return outputCanvas
    }

    async function onPlayed() {
        await updateVideoMasksSmooth()
        await updateVideoSmooth()
    }

    function onPaused() {
        cancelAnimationFrame(maskAnimationFrameId)
        cancelAnimationFrame(videoAnimationFrameId)
    }

    async function onFrameUpdated() {
        await drawVideo()
        await updateVideoMasks()
    }

    async function updateDetectionAndVisibleMasks(newMasks) {
        await nextTick();
        console.warn('updateDetectionAndVisibleMasks called')
        //console.log('RectB:', ...getBoxVideoSize())
        //await new Promise(resolve => setTimeout(resolve, 1000));
        //console.log('RectA:', ...getBoxVideoSize())
        await videoEditor.maskHandler.drawDetectionMasks(maskCanvasRef.value, newMasks, ...getBoxVideoSize());
        await videoEditor.maskHandler.drawVisibleMasks(activeMaskCanvasRef.value, newMasks, ...getBoxVideoSize());
        video.value.backgroundMask = await videoEditor.maskHandler.getBackgroundMask(newMasks, ...getBoxVideoSize());
    }

    async function updateAllCanvasSizes() {
        console.log('updateAllCanvasSizes called')
        const [width, height] = getBoxVideoSize();

        for (const canvas of [videoCanvasRef, maskCanvasRef, activeMaskCanvasRef, colorEffectCanvasRef]) {
            if (canvas.value) {
                canvas.value.width = width;
                canvas.value.height = height;
            }
        }

        videoEditor.maskHandler.clearCanvas(activeMaskCanvasRef.value, width, height);
        await drawVideo();
        await updateVideoMasks();
        await updateDetectionAndVisibleMasks(video.value.masks)
    }

    let resizeObserver = null;
    onMounted(() => {
        video.value = props.video
        video.value.onMetadataLoaded(() => {
            enableResize.value = true

            watch(() => video.value.masks, async (newMasks) => {
                await updateDetectionAndVisibleMasks(newMasks)
            }, { deep: true });

            video.value.onVideoHided(() => {
                videoEditor.maskHandler.clearCanvas(videoCanvasRef.value, ...getBoxVideoSize())
            })

            video.value.onFrameUpdated(onFrameUpdated)

            video.value.element.addEventListener('seeked', async () => {
                await drawVideo();
            }, { once: true });

            nextTick(async () => {
                videoEditor.registerBox(video.value, {
                    // Para obter a própria instância dentro do componente:
                    box: boxVideoRef,
                    getCanvasToApplyColorEffect: () => colorEffectCanvasRef.value,
                    getCanvasToApplyMask: () => maskCanvasRef.value,
                    getCanvasToApplyVideo: () => videoCanvasRef.value,
                    getCanvasToApplyActiveMask: () => activeMaskCanvasRef.value,
                    clearVisibleCanvas: () => {
                        videoEditor.maskHandler.clearCanvas(activeMaskCanvasRef.value, ...getBoxVideoSize())
                        videoEditor.maskHandler.clearCanvas(colorEffectCanvasRef.value, ...getBoxVideoSize())
                    },
                    clearActiveCanvas: () => videoEditor.maskHandler.clearCanvas(activeMaskCanvasRef.value, ...getBoxVideoSize()),
                    getBoxVideoSize: getBoxVideoSize,
                    getRect: (abs = false) => boxVideoRef.value?.getRect(abs),
                    getRotation: () => boxVideoRef.value?.getRotation(),
                    addOnDrawVideoCallback: (id, callback, allow_cache = true) => {
                        drawVideoCallbacksCache.value = {};
                        onDrawVideoCallbacks.value.set(id, {
                            callback,
                            allow_cache
                        })
                    },
                    removeOnDrawVideoCallback: (id) => {
                        drawVideoCallbacksCache.value = {};
                        onDrawVideoCallbacks.value.delete(id)
                    },
                    clearCache: () => {
                        drawVideoCallbacksCache.value = {};
                    },
                    drawVideo: drawVideo,
                    video: video.value,
                    flip: () => boxVideoRef.value?.flip(),
                    getFlip: () => boxVideoRef.value?.getFlip(),
                    updateDetectionAndVisibleMasks: (newMasks) => updateDetectionAndVisibleMasks(newMasks),
                })
                await drawVideo()
            })

            watch(() => video.value.chromaKeyDetectionData, () => {
                nextTick(async () => {
                    await drawVideo()
                })
            }, { deep: true })
        })

        boxVideoRef.value.boxRef.insertBefore(video.value.element, boxVideoRef.value.boxRef.firstChild);
        video.value.element.style.opacity = 0;

        window.addEventListener('keydown', (e) => {
            //if (e.key.toLowerCase() === 'r') {
            //    console.warn('[DEBUG] Limpando todos os onDrawVideoCallbacks');
            //    onDrawVideoCallbacks.value.clear();
            //    drawVideoCallbacksCache.value = {};
            //}
        });

        //resizeObserver = new ResizeObserver(async () => await updateAllCanvasSizes());
        //nextTick(() => resizeObserver.observe(boxVideoRef.value.boxRef))
    });

    onUnmounted(() => {
        console.log('BoxVideo destruído para', props.video?.id);

        resizeObserver?.disconnect();

        // Cancelar animações
        cancelAnimationFrame(maskAnimationFrameId);
        cancelAnimationFrame(videoAnimationFrameId);

        // Remover listeners de eventos, se necessário
        if (video.value?.element) {
            video.value.element.removeEventListener('seeked', drawVideo);
        }

        timelineStore.removeOnPlayed(onPlayed)
        timelineStore.removeOnPaused(onPaused)

        drawVideoCallbacksCache.value = {};
        onDrawVideoCallbacks.value.clear()

        // Limpar referências
        delete videoEditor.mapperBoxVideo[video.value.id];
    });

    defineExpose({
        // Para obter a própria instância dentro do componente:
        boxVideoRef,
    });
</script>

<style scoped>
    .masks-container {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        pointer-events: auto;
    }

    .mask-image {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        opacity: 0;
        pointer-events: none;
        /*transition: opacity 0.2s ease-in-out;
        mix-blend-mode: multiply;
        filter: invert(100%) opacity(0.8);*/
    }

    .mask-canvas {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        pointer-events: none;
        opacity: 0;
    }

    .active-mask-canvas {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        pointer-events: none;
        opacity: 1;
    }

    .color-effect-canvas {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        pointer-events: none;
        opacity: 0.5;
    }

    .video-canvas {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        pointer-events: none;
        border-radius: inherit;
        opacity: 1;
    }

    .point {
        position: absolute;
        display: flex;
        justify-content: center;
        align-items: center;
        width: 1rem;
        height: 1rem;
        font-size: 0.8125rem;
        border-radius: 50%;
        color: white;
        transform: translate(-50%, -50%);
    }

    .add {
        background-color: var(--main-color);
    }

    .remove {
        background-color: #F44336;
    }

    .video-box {
        border: 1px solid transparent;
    }
</style>