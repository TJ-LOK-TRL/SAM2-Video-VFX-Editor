const imageCache = new Map();

// crypto.randomUUID() só existe em secure contexts (HTTPS ou localhost); crypto.getRandomValues()
// não tem essa restrição, por isso serve de fallback para acesso por IP direto em HTTP simples.
export function generateUUID() {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
        return crypto.randomUUID()
    }

    const bytes = crypto.getRandomValues(new Uint8Array(16))
    bytes[6] = (bytes[6] & 0x0f) | 0x40
    bytes[8] = (bytes[8] & 0x3f) | 0x80
    const hex = [...bytes].map(b => b.toString(16).padStart(2, '0')).join('')
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}

export function base64ToBlobURL(base64, mimeType) {
    const byteString = atob(base64.split(',')[1] || base64)
    const ab = new ArrayBuffer(byteString.length)
    const ia = new Uint8Array(ab)
    for (let i = 0; i < byteString.length; i++) {
        ia[i] = byteString.charCodeAt(i)
    }
    return URL.createObjectURL(new Blob([ab], { type: mimeType }))
}

export function base64ToBlob(base64Data) {
    const parts = base64Data.split(';base64,')
    const contentType = parts[0].split(':')[1]
    const byteCharacters = atob(parts[1])
    const byteArrays = []

    for (let i = 0; i < byteCharacters.length; i++) {
        byteArrays.push(byteCharacters.charCodeAt(i))
    }

    return new Blob([new Uint8Array(byteArrays)], { type: contentType })
}

export function loadImageFromCache(url) {
    return new Promise((resolve, reject) => {
        if (imageCache.has(url)) {
            resolve(imageCache.get(url));
        } else {
            const img = new Image();
            img.src = url;
            img.onload = () => {
                imageCache.set(url, img);
                resolve(img);
            };
            img.onerror = (e) => {
                console.error('Erro ao carregar imagem da URL:', url);
                console.error('Evento de erro:', e);
                reject(new Error(`Erro ao carregar imagem da URL: ${url}`));
            };
        }
    });
}

export function updateImageFromCache(url, newImg) {
    imageCache.set(url, newImg);
}

export function resetImageCache(url) {
    imageCache.delete(url);
}

export function hexToRgb(hex) {
    if (typeof hex !== 'string') {
        throw new TypeError('O valor deve ser uma string e não o tipo ' + typeof hex + ' (' + hex + ')');
    }

    // Remove o # se existir
    hex = hex.replace('#', '');

    // Converte 3-digit hex para 6-digit
    if (hex.length === 3) {
        hex = hex.split('').map(c => c + c).join('');
    }

    // Parse para RGB
    const result = /^([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
    return result ? {
        r: parseInt(result[1], 16),
        g: parseInt(result[2], 16),
        b: parseInt(result[3], 16)
    } : null;
}

export function rgbToHsl(r, g, b) {
    r /= 255, g /= 255, b /= 255;

    const max = Math.max(r, g, b);
    const min = Math.min(r, g, b);
    let h, s, l = (max + min) / 2;

    if (max === min) {
        h = s = 0; // Achromatic (grayscale)
    } else {
        const d = max - min;
        s = l > 0.5 ? d / (2 - max - min) : d / (max + min);

        switch (max) {
            case r: h = (g - b) / d + (g < b ? 6 : 0); break;
            case g: h = (b - r) / d + 2; break;
            case b: h = (r - g) / d + 4; break;
        }
        h /= 6;
    }

    return [h, s, l];
}

export function hslToRgb(h, s, l) {
    let r, g, b;

    if (s === 0) {
        r = g = b = l; // achromatic
    } else {
        const hue2rgb = (p, q, t) => {
            if (t < 0) t += 1;
            if (t > 1) t -= 1;
            if (t < 1 / 6) return p + (q - p) * 6 * t;
            if (t < 1 / 2) return q;
            if (t < 2 / 3) return p + (q - p) * (2 / 3 - t) * 6;
            return p;
        };

        const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
        const p = 2 * l - q;
        r = hue2rgb(p, q, h + 1 / 3);
        g = hue2rgb(p, q, h);
        b = hue2rgb(p, q, h - 1 / 3);
    }

    return [Math.round(r * 255), Math.round(g * 255), Math.round(b * 255)]
}

export function getGaussianKernel(radius) {
    const kernel = [];
    let sum = 0;
    const sigma = radius / 3; // Relação padrão entre radius e sigma

    for (let i = -radius; i <= radius; i++) {
        const value = Math.exp(-(i * i) / (2 * sigma * sigma));
        kernel.push(value);
        sum += value;
    }

    // Normaliza o kernel
    return kernel.map(v => v / sum);
}

export function joinTrackedMasks(existingMasks, newMasks) {
    const merged = { ...existingMasks };

    for (const frameIdx in newMasks) {
        if (!merged[frameIdx]) {
            merged[frameIdx] = {};
        }

        for (const objId in newMasks[frameIdx]) {
            merged[frameIdx][objId] = newMasks[frameIdx][objId];
        }
    }

    return merged;
}

/**
 * Corrige um DOMRect visual (com zoom) para valores lógicos, compensando o scale.
 * @param {DOMRect} rect - O bounding rect retornado por getBoundingClientRect().
 * @param {number} zoom - O fator de zoom (ex: 0.5 se for transform: scale(0.5)).
 * @returns {{ width: number, height: number, left: number, top: number }}
 */
export function getRectWithZoom(e, zoom) {
    const rect = e.getBoundingClientRect()

    return {
        width: rect.width / zoom,
        height: rect.height / zoom,
        left: rect.left / zoom,
        top: rect.top / zoom
    }
}

export function getStageNameOfVideo(video, suffix) {
    if (!video.use_cache) {
        return null
    }

    return video.file.name + suffix
}

export function calculateTimeByFrameIdx(frameIdx, fps) {
    if (frameIdx < 0) {
        return 0
    }

    const frameDuration = 1 / fps;

    // Cálculo preciso do tempo
    let targetTime = frameIdx / fps;
    const targetTimeTruncated = Math.floor(targetTime * 1e6) / 1e6; // Irritante

    // Verificação de precisão
    if (Math.floor(targetTimeTruncated * fps) < frameIdx) {
        // Ajuste preciso de meio frame duration
        const safeAdjustment = (frameDuration / 2) * 0.999; // Fator de segurança extra
        targetTime = targetTime + safeAdjustment;
        console.log(`Ajustando seek: +${safeAdjustment} (metade do frame duration com margem)`);
    }

    return targetTime
}

// DO NOT WORK WELL; NOT USED ANYMORE; COULD BE REMOVED
export function getOriginalDimensions(bounds, rotation) {
    const { x, y, width: w, height: h } = bounds

    // bounds is a POJO with shape: { x, y, w, h }, update if needed
    // alpha is the rotation IN RADIANS
    const vertices = (alpha) => {
        const
            A = { x: x + w * Math.sin(alpha), y },
            B = { x, y: y + h * Math.sin(alpha) },
            C = { x: x + w - w * Math.sin(alpha), y },
            D = { x, y: y + h - h * Math.sin(alpha) }
        return { A, B, C, D }
    }

    // bounds is a POJO with shape: { x, y, w, h }, update if needed
    // vertices is a POJO with shape: { A, B, C, D }, as returned by the `vertices` method
    const sides = (vertices) => {
        const { A, B, C, D } = vertices,
            EA = A.x - x,
            ED = D.y - y,
            AF = w - EA,
            FB = h - ED,
            H = Math.sqrt(EA * EA + ED * ED),
            W = Math.sqrt(AF * AF + FB * FB)
        return { h: H, w: W }
    }

    // bounds is a POJO with shape: { x, y, w, h }, update if needed
    // sides is a POJO with shape: { w, h }, as returned by the `sides` method
    const originPoint = (sides) => {
        const { w: W, h: H } = sides
        const GC = Math.sqrt(W * W + H * H) / 2,
            r = Math.sqrt(W * W + H * H) / 2,
            IC = H / 2,
            beta = Math.asin(IC / GC),
            angleA = Math.PI + beta,
            Ax = x + w / 2 + r * Math.cos(angleA),
            Ay = y + h / 2 + r * Math.sin(angleA)
        return { newX: Ax, newY: Ay }
    }

    // bounds is a POJO with shape: { x, y, w, h }, update if needed
    // rotations is... the rotation of the inner rectangle IN RADIANS
    const radians = Math.PI / 180 * rotation;
    const points = vertices(radians)
    const dimensions = sides(points)
    const { newX, newY } = originPoint(dimensions)
    return { ...dimensions, left: newX, top: newY }
}

export function getRotation(element) {
    const style = window.getComputedStyle(element);
    const matrix = new DOMMatrix(style.transform);
    return Math.atan2(matrix.b, matrix.a) * (180 / Math.PI);
}

// CAN BE REMOVED
window.getOriginalDimensions = getOriginalDimensions