import { defineStore } from "pinia"
import { computed, ref } from "vue"
import { useBackendStore } from "/src/stores/backend.js"
import ImageMedia from "/src/assets/js/videoEditor/media/ImageMedia.js"
import VideoMedia from "/src/assets/js/videoEditor/media/VideoMedia.js"
import AudioMedia from "/src/assets/js/videoEditor/media/AudioMedia.js"
import TextElement from "/src/assets/js/videoEditor/TextElement.js"
import MaskHandler from "/src/assets/js/maskHandler.js"
import AnimationHandler from "/src/assets/js/animationHandler"
import EffectHandler from "/src/assets/js/effectHandler.js"
import EditorElementManager from "/src/assets/js/videoEditor/EditorElementManager.js"
import { VideoEditorRegister } from "/src/assets/js/videoEditorRegister"
import { base64ToBlob } from "/src/assets/js/utils.js"

export const useVideoEditor = defineStore('videoEditor', () => {
    const backend = useBackendStore()
    const elementManager = ref(new EditorElementManager())
    const register = ref(new VideoEditorRegister())
    const maskHandler = ref(new MaskHandler())
    const animationHandler = ref(new AnimationHandler(register.value))
    const effectHandler = ref(new EffectHandler(register.value, maskHandler.value))

    const isLoadingInternal = ref(false); // Estado interno
    const loadingStatusText = ref('') // Texto de status mostrado durante o loading (ex.: progresso de uma task assíncrona)

    // Computed com getter e setter para rastrear mudanças
    const isLoading = computed({
        get() {
            return isLoadingInternal.value;
        },
        set(newValue) {
            //console.log(`isLoading está sendo alterado de ${isLoadingInternal.value} para ${newValue}`);
            //console.trace("Stack trace da modificação"); // Mostra onde a mudança ocorreu
            isLoadingInternal.value = newValue;
        }
    });

    const videoPlayerContainer = ref(null)
    const videoPlayerSpaceContainer = ref(null)
    const videoPlayerWidth = ref(null)
    const videoPlayerHeight = ref(null)
    const videoPlayerWidthResized = ref(null)
    const videoPlayerHeightResized = ref(null)

    const selectedElement = ref(null)
    const onEditorElementSelectedCallbacks = ref(new Map())
    const onFirstVideoMetadataLoadedCallbacks = ref([])
    const onVideoMetadataLoadedCallbacks = ref([])

    const onElementAddedCallbacks = ref([])
    const onElementRemovedCallbacks = ref(new Map());

    const selectedTool = ref('')
    const selectedToolIcon = ref('')
    const selectedToolHistory = ref([])

    const mapperBoxVideo = ref({})
    const onAddMapBoxVideoCallbacks = ref([])
    const fps = ref(null)
    const maskScaleFactor = ref(0.5)
    const onCompileVideoMetadataCallbacks = ref(new Map())
    const zoomLevel = ref(1)

    const preventUnselectElementOnOutside = ref(false)

    const isPromptElementOpen = ref(false)
    const onElementPromptedSelectCallback = ref(null)
    const onElementPromptSelectionDoneCallback = ref(null)

    const lines = ref(new Map())

    function createVideo(file, fps, frames) {
        const video = new VideoMedia(file, fps, frames)
        elementManager.value.addElement(video)

        video.onMetadataLoaded(() => {
            if (elementManager.value.getByType('video').length == 1) {
                videoPlayerWidth.value = video.width
                videoPlayerHeight.value = video.height
                onFirstVideoMetadataLoadedCallbacks.value.forEach(callback => callback(video))
            }

            onVideoMetadataLoadedCallbacks.value.forEach(callback => callback(video))
        })

        onElementAddedCallbacks.value.forEach(callback => callback(video))

        return video
    }

    async function addVideo(file) {
        if (file.type.startsWith('image/')) {
            file = await convertImageToVideo(file)
        }

        const metadata = await getVideoMetadata(file)
        return createVideo(file, metadata.fps, metadata.frames)
    }

    function addText(text, preset, font, fontSize = '16px') {
        const textElement = new TextElement(text, preset, font, fontSize)
        elementManager.value.addElement(textElement)

        onElementAddedCallbacks.value.forEach(callback => callback(textElement))
        return textElement
    }

    function removeElement(editorElement) {
        if (!editorElement) {
            console.warn('Invalid editorElement in removeElement:', editorElement)
            return
        }

        if (selectedElement?.value?.id == editorElement?.id) {
            selectedElement.value = null
        }

        if (maskHandler.value?.video?.id === editorElement?.id) {
            maskHandler.value.video = null
        }

        elementManager.value.removeElement(editorElement)
        if (editorElement.type === 'video') {
            const video = editorElement
            delete mapperBoxVideo.value[video.id]
            video.masks.forEach(mask => {
                URL.revokeObjectURL(mask.url)
            })
            Object.values(video.trackMasks).forEach(frameObj => {
                Object.values(frameObj).forEach(trackMask => {
                    URL.revokeObjectURL(trackMask.url)
                })
            })
            console.log('Removed video id ' + video.id)

            // 📋 Debug extra: mostra todos os vídeos restantes
            const remainingVideos = getVideos()
            console.log('Remaining video IDs:', remainingVideos.map(v => v.id))

            video.delete()
        }

        onElementRemovedCallbacks.value.forEach((callback, id) => callback(editorElement))
    }

    function cloneVideo(video, onAddBoxCallback) {
        const newVideo = createVideo(video.file, video.fps, video.frames)

        onAddMapBoxVideo((_newVideo, box) => {
            if (newVideo.id === _newVideo.id) {
                const flipped = getFlipStateOfVideo(video)
                if (flipped) box.flip()

                newVideo.track_id = video.track_id
                newVideo.trackMasks = JSON.parse(JSON.stringify(video.trackMasks))
                newVideo.masks = JSON.parse(JSON.stringify(video.masks))
                box.updateDetectionAndVisibleMasks(JSON.parse(JSON.stringify(video.masks)))

                onAddBoxCallback?.(newVideo, box)
            }
        })

        return newVideo
    }

    async function convertImageToVideo(file) {
        const blob = await backend.convertImageToVideo(file)
        const fileFromBlob = new File([blob], 'converted.mp4', { type: 'video/mp4' });
        return fileFromBlob
    }

    async function getVideoMetadata(file) {
        if (!file) return

        const basicData = await backend.getMediaBasicData(file)

        // Os frames vÊm em base64 naturalmente, então precisamos converter para passar no URL
        basicData.frames = basicData.frames.map(base64 => {
            const byteString = atob(base64.split(',')[1] || base64)
            const mimeString = "image/jpeg"

            const ab = new ArrayBuffer(byteString.length)
            const ia = new Uint8Array(ab)
            for (let i = 0; i < byteString.length; i++) {
                ia[i] = byteString.charCodeAt(i)
            }

            const blob = new Blob([ab], { type: mimeString })
            return URL.createObjectURL(blob)
        })
        console.log("Video basic data:", basicData)

        return basicData
    }

    async function generateMasksForFrame(frameBlob) {
        const data = await backend.getMasksForFrame(frameBlob)

        const imageBlob = base64ToBlob(data.image)
        const imageURL = URL.createObjectURL(imageBlob)

        const masks = data.masks.map(mask => {
            const maskBlob = base64ToBlob(mask.mask)
            return {
                id: mask.id,
                url: URL.createObjectURL(maskBlob)
            }
        })

        return {
            imageURL,
            masks
        }
    }

    const maskJobStageLabels = {
        pending: 'A preparar pedido...',
        downloading: 'A carregar vídeo...',
        segmenting: 'A gerar máscaras com SAM2...',
        finishing: 'A finalizar...',
    }

    // Generates masks for the video
    async function generateMasksForVideo(video, inputOptions = {}, usePoints = null) {
        const ann_frame_idx = Math.floor(video.currentTime * video.fps);
        const rawPoints = usePoints || video.points;

        const options = {
            scale_factor: inputOptions.scale_factor || maskScaleFactor.value,
            ...inputOptions,
            onStatusUpdate: (statusData) => {
                loadingStatusText.value = maskJobStageLabels[statusData.stage] || maskJobStageLabels[statusData.status] || ''
            },
        };

        // Agrupar pontos por objId
        const grouped = {};
        for (const point of rawPoints) {
            const objId = point.objId;  // fallback para 1 se não estiver definido
            if (!grouped[objId]) {
                grouped[objId] = [];
            }
            grouped[objId].push(point);
        }

        // Construir lista de videoObjects
        const videoObjectsInfo = Object.entries(grouped).map(([objId, groupPoints]) => {
            return {
                points: groupPoints.map(p => [p.realX, p.realY]),
                labels: groupPoints.map(p => (p.type === 'add' ? 1 : 0)),
                ann_frame_idx,
                ann_obj_id: parseInt(objId)
            };
        });

        try {
            const data = await backend.getMasksForVideo(video.file, videoObjectsInfo, options)

            const newMasks = {}
            Object.keys(data.result).forEach(frameIdx => {
                const frameData = data.result[frameIdx];
                const newFrameIdx = parseInt(frameIdx);

                if (!newMasks[newFrameIdx]) {
                    newMasks[newFrameIdx] = {};
                }

                Object.keys(frameData).forEach(objId => {
                    const maskData = frameData[objId];
                    const maskBlob = base64ToBlob(maskData.data, 'image/png');
                    const maskURL = URL.createObjectURL(maskBlob);
                    const originalMaskURL = URL.createObjectURL(maskBlob);

                    const newMask = {
                        id: `${newFrameIdx}-${objId}`,
                        objId: objId,
                        frameIdx: newFrameIdx,
                        shape: maskData.shape,
                        url: maskURL,
                        originalUrl: originalMaskURL, // Util when url changes and we want the original maskURL
                        videoId: video.id,
                    };

                    newMasks[newFrameIdx][objId] = newMask;
                    //console.log(`Mask generated for frame ${newFrameIdx}, objId ${objId}:`, newMask);
                });
            });

            return [data.track_id, newMasks];
        }
        catch (error) {
            console.error('Erro ao gerar máscaras para o vídeo:', error);
            alert(`Ocorreu um erro ao gerar as máscaras do vídeo: ${error.message || error}`);
            return null;
        }
        finally {
            loadingStatusText.value = ''
        }
    }

    function getVideos() {
        return elementManager.value.getByType('video')
    }

    function getTexts() {
        return elementManager.value.getByType('text')
    }

    function getElements() {
        return elementManager.value.listElements()
    }

    function setVideoPlayerContainer(e) {
        videoPlayerContainer.value = e
    }

    function setVideoPlayerSpaceContainer(e) {
        videoPlayerSpaceContainer.value = e
    }

    function setVideoPlayerSize(width, height) {
        //videoPlayerWidth.value = width
        //videoPlayerHeight.value = height
        videoPlayerWidthResized.value = width
        videoPlayerHeightResized.value = height
    }

    function getVideoPlayerSize() {
        return {
            width: videoPlayerWidthResized.value, //Math.min(videoPlayerWidthResized.value, 1000),
            height: videoPlayerHeightResized.value
        }
    }

    function selectEditorElement(editorElement) {
        selectedElement.value = editorElement
        for (const callback of onEditorElementSelectedCallbacks.value.values()) {
            callback(editorElement)
        }
    }

    function onEditorElementSelected(id, callback) {
        onEditorElementSelectedCallbacks.value.set(id, callback)
    }

    function removeOnEditorElementSelected(id) {
        onEditorElementSelectedCallbacks.value.delete(id)
    }

    function onFirstVideoMetadataLoaded(callback) {
        onFirstVideoMetadataLoadedCallbacks.value.push(callback)
    }

    function removeOnFirstVideoMetadataLoaded(callback) {
        onFirstVideoMetadataLoadedCallbacks.value = onFirstVideoMetadataLoadedCallbacks.value.filter(cb => cb !== callback)
    }

    function onVideoMetadataLoaded(callback) {
        onVideoMetadataLoadedCallbacks.value.push(callback)
    }

    function removeOnVideoMetadataLoaded(callback) {
        onVideoMetadataLoadedCallbacks.value = onVideoMetadataLoadedCallbacks.value.filter(cb => cb !== callback)
    }

    function onElementAdded(callback) {
        onElementAddedCallbacks.value.push(callback)
    }

    function onElementRemoved(id, callback) {
        onElementRemovedCallbacks.value.set(id, callback);
    }

    function removeOnElementRemoved(id) {
        onElementRemovedCallbacks.value.delete(id);
    }

    function reorderElements(currentId, targetId) {
        const allElements = elementManager.value.listElements();

        const currentIndex = allElements.findIndex(el => el.id === currentId);
        const targetIndex = allElements.findIndex(el => el.id === targetId);

        if (currentIndex === -1 || targetIndex === -1) return;

        const [movedElement] = allElements.splice(currentIndex, 1);
        allElements.splice(targetIndex, 0, movedElement);

        // Reconstroi os maps baseados na nova ordem
        elementManager.value.elementsById.clear();
        elementManager.value.elementsByType.clear();

        for (const el of allElements) {
            elementManager.value.addElement(el);
        }
    }

    function changeTool(newTool, newToolIcon = null) {
        const newIcon = newToolIcon === null ? selectedToolIcon.value : newToolIcon

        // Só adiciona ao histórico se for diferente da última entrada
        const last = selectedToolHistory.value.at(-1)
        if (!last || last.selectedTool !== selectedTool.value || last.selectedToolIcon !== selectedToolIcon.value) {
            selectedToolHistory.value.push({
                selectedTool: selectedTool.value,
                selectedToolIcon: selectedToolIcon.value
            })
        }

        selectedTool.value = newTool
        selectedToolIcon.value = newIcon
        //console.warn('change Location:', newTool, newIcon)
    }

    function changeToPreviousTool() {
        if (selectedToolHistory.value.length === 0) return;

        const last = selectedToolHistory.value.pop();
        selectedTool.value = last.selectedTool;
        selectedToolIcon.value = last.selectedToolIcon;
        //console.warn('changeToPreviousTool:', selectedTool.value, selectedToolIcon.value)
    }

    function getBoxOfElement(element) {
        if (!mapperBoxVideo.value[element?.id]) {
            return null
        }

        return mapperBoxVideo.value[element.id]
    }

    function getRectBoxOfElement(element, abs = false) {
        const boxElement = getBoxOfElement(element);
        if (!boxElement) {
            console.warn('getRectBoxOfElement: Nenhum box encontrado para o vídeo.', element);
            return null;
        }

        const rect = boxElement.box.getRect(abs);
        if (!rect) {
            console.warn('getRectBoxOfElement: A função getRect retornou null ou undefined.', boxElement, abs);
            return null;
        }

        return rect;
    }

    function getFlipStateOfVideo(element) {
        const box = getBoxOfElement(element)
        if (!box) {
            return null
        }

        const flip = box.getFlip()
        if (!flip) {
            return null
        }

        return flip
    }

    function getRotationOfElement(element) {
        const boxElement = getBoxOfElement(element)
        if (!boxElement) {
            return null
        }

        return boxElement.box.getRotation()
    }

    function getOpacityOfElement(element) {
        const boxElement = getBoxOfElement(element)
        if (!boxElement) {
            return null
        }

        return boxElement.box.opacity
    }

    function getElementBorderRadius(element) {
        const boxElement = getBoxOfElement(element)
        if (!boxElement) {
            return null
        }

        return boxElement.box.roundedCorner
    }

    async function getCompileVideoMetadata(metadata, video) {
        for (const callback of onCompileVideoMetadataCallbacks.value.values()) {
            const newMetadata = await callback(metadata, video);
            if (newMetadata !== null && newMetadata !== undefined) {
                metadata = newMetadata;
            }
        }
        return metadata;
    }

    function onCompileVideoMetadata(id, callback) {
        onCompileVideoMetadataCallbacks.value.set(id, callback);
    }

    function removeOnCompileVideoMetadataCallback(id) {
        onCompileVideoMetadataCallbacks.value.delete(id);
    }

    async function compileVideos(elements, compute_transparency = false, width = null, height = null) {
        try {
            if (!elements || elements.length === 0) {
                console.error("Nenhum vídeo encontrado para compilar.");
                return null;
            }

            isLoading.value = true;

            const output_width = width || videoPlayerWidthResized.value
            const output_height = height || videoPlayerHeightResized.value
            const metadata = {
                width: output_width,
                height: output_height,
                fps: fps.value,
                enable_transparency: compute_transparency,
                elements_data: {},
            };

            const videos_files = [];
            for (let index = 0; index < elements.length; index++) {
                const element = elements[index];
                const { x, y, width, height } = getRectBoxOfElement(element);

                const element_data = {
                    x: x,
                    y: y,
                    width: width,
                    height: height,
                    layer_idx: index,
                    st_offset: element.stOffset,
                    start_t: element.start,
                    end_t: element.end,
                    speed: element.speed,
                    draw: element.shouldBeDraw,
                    type: element.type,
                    flipped: getFlipStateOfVideo(element),
                    rotation: getRotationOfElement(element),
                    borderRadius: getElementBorderRadius(element),
                    effects: register.value.getLastEffectOfVideo(element.id),
                    opacity: compute_transparency ? getOpacityOfElement(element) : 1,
                    animations: compute_transparency ? register.value.getAnimations(element.id) : []
                }

                if (element.type === 'video') {
                    Object.assign(element_data, {
                        stageMasks: element.track_id,
                        chromaKeyDetectionData: element.chromaKeyDetectionData,
                    });

                    videos_files.push(element.file);
                } else if (element.type === 'text') {
                    const copy_style = JSON.parse(JSON.stringify(element.style));
                    copy_style.fontSize = parseInt(copy_style.fontSize.replace('px', ''), 10);
                    Object.assign(element_data, {
                        text: element.text,
                        style: copy_style,
                    });
                }
                metadata.elements_data[element.id] = await getCompileVideoMetadata(element_data, element);

                console.log("Element data:", metadata.elements_data[element.id]);
            }

            const data = await backend.download(videos_files, metadata);
            return data

        } catch (error) {
            console.error('Erro durante o download:', error);
            return null; // Retorna null ou um valor padrão em caso de erro
            // Você pode adicionar tratamento de erro visual aqui
        } finally {
            isLoading.value = false;
        }
    }

    function download(data, filename = 'final_video.mp4') {
        // Cria o link de download
        const url = window.URL.createObjectURL(new Blob([data]));
        const link = document.createElement('a');
        link.href = url;
        link.setAttribute('download', filename);
        document.body.appendChild(link);
        link.click();

        setTimeout(() => {
            document.body.removeChild(link);
            window.URL.revokeObjectURL(url);
        }, 100);
    }

    function exportProject() {
        return {
            videos: this.getVideos().map(video => {
                const box = getBoxOfElement(video)
                return {
                    id: video.id,
                    file: video.file,
                    fps: video.fps,
                    start: video.start,
                    end: video.end,
                    position: box ? box.getRect() : null,
                    flipped: getFlipStateOfVideo(video),
                    rotation: getRotationOfElement(video),
                }
            }),
            timeline: this.timeline,
            zoomLevel: this.zoomLevel,
        }
    }

    async function importProject(projectData) {
        try {

            // verificar estrutura de dados do projeto
            console.log("Dados recebidos no importProject:", projectData)

            // limpar editor
            this.clearEditor()
            if (!projectData || !projectData.videos || !Array.isArray(projectData.videos)) {
                throw new Error("Dados do projeto inválidos ou ausentes.");
            }

            // carrega os videos do projeto
            for (const videoData of projectData.videos) {
                if (!videoData.file) {
                    throw new Error("Dados do vídeo inválidos ou ausentes.");
                }
                const video = await this.addVideo(videoData.file)

                // propriedades do video
                if (videoData.start !== undefined) video.start = videoData.start
                if (videoData.end !== undefined) video.end = videoData.end
                if (videoData.speed !== undefined) video.speed = videoData.speed

                // configurar posiçao e transformaçoes
                const box = this.mapperBoxVideo[video.id]

                if (box) {
                    if (videoData.position) {
                        box.setRect(videoData.position)
                    }
                    if (videoData.rotation) {
                        box.setRotation(videoData.rotation)
                    }
                    if (videoData.flipped) {
                        box.setFlip(videoData.flip)
                    }
                }

                // aplicar efeitos se existirem
                if (videoData.effects)
                    this.register.applyEffectsToVideo(video.id, videoData.effects)


            }
            return true
        } catch (error) {
            console.error('Erro ao importar projeto:', error);
            return false
        }

    }
    function clearEditor() {
        // Remove todos os vídeos
        this.getVideos().forEach(video => {
            try {
                this.removeElement(video);
            } catch (e) {
                console.error('Erro ao remover vídeo:', e);
            }
        });

        // Remove todos os textos
        this.getTexts().forEach(text => {
            try {
                this.removeElement(text);
            } catch (e) {
                console.error('Erro ao remover texto:', e);
            }
        });

        // Reseta estados
        this.selectedElement = null;
        this.mapperBoxVideo = {};
        this.zoomLevel = 1;
    }
    function onAddMapBoxVideo(callback) {
        onAddMapBoxVideoCallbacks.value.push(callback)
    }

    function removeOnAddMapBoxVideo(callback) {
        const index = onAddMapBoxVideoCallbacks.value.indexOf(callback);
        if (index !== -1) {
            onAddMapBoxVideoCallbacks.value.splice(index, 1);
        }
    }

    function registerBox(element, box) {
        mapperBoxVideo.value[element.id] = box
        onAddMapBoxVideoCallbacks.value.forEach(callback => {
            callback(element, box)
        })
    }

    function promptElementSelection(onElementSelected, onElementPromptSelectionDone) {
        isPromptElementOpen.value = true
        onElementPromptedSelectCallback.value = onElementSelected
        onElementPromptSelectionDoneCallback.value = onElementPromptSelectionDone
    }

    function dialogError(msg) {

    }

    function addAnimationLine(id, points, allowModification = false, visible = true) {
        lines.value.set(id, { id, points, allowModification, visible })
    }

    return {
        elementManager, isLoading, loadingStatusText, videoPlayerWidth, videoPlayerHeight, videoPlayerContainer, fps,
        selectedElement, maskHandler, selectedTool, selectedToolIcon, mapperBoxVideo, register, effectHandler, zoomLevel,
        preventUnselectElementOnOutside, videoPlayerSpaceContainer, maskScaleFactor, isPromptElementOpen, onElementPromptedSelectCallback,
        onElementPromptSelectionDoneCallback, animationHandler, lines,
        addVideo, addText, cloneVideo, getVideos, getTexts, getElements, generateMasksForFrame, selectEditorElement, setVideoPlayerContainer,
        onFirstVideoMetadataLoaded, removeOnFirstVideoMetadataLoaded, onEditorElementSelected, onVideoMetadataLoaded,
        removeOnVideoMetadataLoaded, reorderElements, generateMasksForVideo,
        removeOnEditorElementSelected, changeTool, changeToPreviousTool, removeElement, getBoxOfElement, download, getVideoMetadata,
        compileVideos, onElementAdded, onElementRemoved, registerBox, onAddMapBoxVideo, removeOnAddMapBoxVideo, getRectBoxOfElement,
        setVideoPlayerSize, onCompileVideoMetadata, getFlipStateOfVideo, exportProject, importProject, setVideoPlayerSpaceContainer,
        removeOnElementRemoved, getVideoPlayerSize, removeOnCompileVideoMetadataCallback, promptElementSelection, dialogError, addAnimationLine
    }
})