import { generateUUID } from "/src/assets/js/utils.js"

export default class EditorElement {
    constructor(type) {
        this.type = type
        this.id = generateUUID()
        this.stOffset = 0
        this.start = 0
        this.end = 5 // Default duration
        this.speed = 1 // Default speed

        // Define o limite máximo visível do timeline (ex: 30s mesmo que o vídeo esteja cortado para this.end=15s).
        // Útil para permitir expandir o vídeo até o ponto original, a menos que maxEnd seja explicitamente reduzido.
        this.maxEnd = 5

        this.shouldBeDraw = true

        Object.defineProperty(this, 'duration', {
            get() {
                return this.end - this.start;
            }
        });
    }

    destroy() {
        console.log(`Destroying element: ${this.id} (${this.type})`)
    }
}
