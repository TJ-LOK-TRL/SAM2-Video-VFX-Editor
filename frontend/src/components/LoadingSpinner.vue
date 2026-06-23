<template>
    <div v-if="isLoading" class="loading-overlay">
        <div class="spinner"></div>
        <p class="loading-text">Loading...</p>
        <p v-if="statusText" class="loading-status-text">{{ statusText }}</p>
        <button v-if="onCancel" class="cancel-loading-button" @click="onCancel">Cancelar</button>
    </div>
</template>

<script setup>
    import { ref, watch } from 'vue';

    const props = defineProps({
        isLoading: Boolean,
        statusText: {
            type: String,
            default: ''
        },
        onCancel: {
            type: Function,
            default: null
        }
    });

    const isLoading = ref(props.isLoading)
    const onCancel = ref(props.onCancel)

    watch(() => props.isLoading, () => {
        isLoading.value = props.isLoading
    })

    watch(() => props.onCancel, () => {
        onCancel.value = props.onCancel
    })
</script>

<style scoped>
    .loading-overlay {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        background: rgba(0, 0, 0, 0.75);
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        z-index: 1000;
    }

    .spinner {
        width: 50px;
        height: 50px;
        border: 5px solid rgba(255, 255, 255, 0.3);
        border-top-color: white;
        border-radius: 50%;
        animation: spin 1s linear infinite;
    }

    .loading-text {
        margin-top: 10px;
        color: white;
        font-size: 18px;
        font-weight: bold;
        text-shadow: 1px 1px 3px rgba(0, 0, 0, 0.5);
    }

    .loading-status-text {
        margin-top: 6px;
        color: rgba(255, 255, 255, 0.8);
        font-size: 14px;
        text-shadow: 1px 1px 3px rgba(0, 0, 0, 0.5);
    }

    .cancel-loading-button {
        margin-top: 16px;
        padding: 8px 20px;
        border: 1px solid rgba(255, 255, 255, 0.4);
        border-radius: 6px;
        background: transparent;
        color: white;
        font-size: 14px;
        cursor: pointer;
    }

    .cancel-loading-button:hover {
        background: rgba(255, 255, 255, 0.15);
    }

    @keyframes spin {
        from {
            transform: rotate(0deg);
        }

        to {
            transform: rotate(360deg);
        }
    }
</style>