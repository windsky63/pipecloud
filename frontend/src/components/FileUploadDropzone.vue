<script setup>
import { computed, ref } from 'vue'
import { t } from '../services/pipecloudState'

const props = defineProps({
  files: { type: Array, default: () => [] },
  accept: { type: String, default: '' },
  multiple: { type: Boolean, default: true },
  disabled: { type: Boolean, default: false },
  title: { type: String, default: '' },
  hint: { type: String, default: '' },
  maxDisplayFiles: { type: Number, default: 5 },
})

const emit = defineEmits(['files-selected'])
const fileInput = ref(null)
const folderInput = ref(null)

const fileNames = computed(() => props.files.map((file) => file.name))
const visibleFiles = computed(() => {
  const limit = Number.isFinite(props.maxDisplayFiles) && props.maxDisplayFiles > 0
    ? props.maxDisplayFiles
    : props.files.length
  return props.files.slice(0, limit)
})
const hiddenFileCount = computed(() => Math.max(props.files.length - visibleFiles.value.length, 0))

function triggerFilePicker() {
  if (props.disabled) return
  fileInput.value?.click()
}

function triggerFolderPicker() {
  if (props.disabled) return
  folderInput.value?.click()
}

defineExpose({
  openFilePicker: triggerFilePicker,
  openFolderPicker: triggerFolderPicker,
})

function emitFiles(files) {
  emit('files-selected', Array.from(files || []))
}

function handleFileSelection(event) {
  emitFiles(event.target.files)
  event.target.value = ''
}

function handleFolderSelection(event) {
  emitFiles(event.target.files)
  event.target.value = ''
}

function handleFileDrop(event) {
  if (props.disabled) return
  emitFiles(event.dataTransfer?.files)
}
</script>

<template>
  <div
    class="file-upload-dropzone"
    :class="{ 'is-disabled': disabled, 'has-files': files.length }"
    role="button"
    tabindex="0"
    @click="triggerFilePicker"
    @keydown.enter.prevent="triggerFilePicker"
    @keydown.space.prevent="triggerFilePicker"
    @dragover.prevent
    @drop.prevent="handleFileDrop"
  >
    <v-icon icon="mdi-cloud-upload-outline" size="42" />
    <input
      ref="fileInput"
      type="file"
      :accept="accept"
      :multiple="multiple"
      hidden
      @click.stop
      @change="handleFileSelection"
    />
    <input
      ref="folderInput"
      type="file"
      :accept="accept"
      webkitdirectory
      directory
      multiple
      hidden
      @click.stop
      @change="handleFolderSelection"
    />
    <div class="file-upload-dropzone-content">
      <strong>{{ files.length ? t('filesSelected') : (title || t('clickOrDropFile')) }}</strong>
      <span>{{ hint || t('clickAgainToReselect') }}</span>
      <div v-if="fileNames.length" class="file-upload-chips">
        <v-chip
          v-for="file in visibleFiles"
          :key="`${file.name}-${file.size}-${file.lastModified}`"
          size="small"
          color="primary"
          variant="tonal"
        >
          {{ file.name }}
        </v-chip>
        <v-chip
          v-if="hiddenFileCount"
          size="small"
          color="secondary"
          variant="tonal"
        >
          +{{ hiddenFileCount }}
        </v-chip>
      </div>
    </div>
  </div>
</template>

<style scoped>
.file-upload-dropzone {
  display: grid;
  grid-template-columns: 56px minmax(0, 1fr);
  gap: 14px;
  align-items: center;
  padding: 18px;
  border: 1px dashed color-mix(in srgb, var(--primary) 48%, var(--line));
  border-radius: 8px;
  background: color-mix(in srgb, var(--primary) 7%, var(--panel));
  cursor: pointer;
  transition: border-color .18s ease, background-color .18s ease, box-shadow .18s ease;
  user-select: none;
}

.file-upload-dropzone:hover,
.file-upload-dropzone:focus-visible {
  border-color: var(--primary);
  background: color-mix(in srgb, var(--primary) 11%, var(--panel));
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--primary) 14%, transparent);
  outline: none;
}

.file-upload-dropzone.is-disabled {
  cursor: progress;
  opacity: .72;
}

.file-upload-dropzone.has-files {
  border-style: solid;
}

.file-upload-dropzone > .v-icon {
  color: var(--primary);
}

.file-upload-dropzone-content {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.file-upload-dropzone-content strong {
  color: var(--strong);
  font-size: 15px;
}

.file-upload-dropzone-content span {
  color: var(--muted);
  font-size: 13px;
}

.file-upload-chips {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 4px;
}

</style>
