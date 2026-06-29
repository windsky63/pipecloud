<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  modelValue: {
    type: [Array, String, Date],
    default: () => [],
  },
  multiple: {
    type: Boolean,
    default: false,
  },
  min: {
    type: String,
    default: '',
  },
  max: {
    type: String,
    default: '',
  },
  highlightedDates: {
    type: Array,
    default: () => [],
  },
  disabled: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['update:modelValue'])

const monthNames = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']
const weekdayLabels = ['一', '二', '三', '四', '五', '六', '日']

function formatDate(value) {
  if (!value) return ''
  if (value instanceof Date && !Number.isNaN(value.getTime())) {
    const year = value.getFullYear()
    const month = String(value.getMonth() + 1).padStart(2, '0')
    const day = String(value.getDate()).padStart(2, '0')
    return `${year}-${month}-${day}`
  }
  const text = String(value).trim()
  const match = text.match(/^(\d{4})-?(\d{2})-?(\d{2})/)
  return match ? `${match[1]}-${match[2]}-${match[3]}` : ''
}

function parseDate(value) {
  const text = formatDate(value)
  if (!text) return null
  const [year, month, day] = text.split('-').map(Number)
  const date = new Date(year, month - 1, day)
  return Number.isNaN(date.getTime()) ? null : date
}

function addMonths(date, amount) {
  return new Date(date.getFullYear(), date.getMonth() + amount, 1)
}

function monthKey(date) {
  return date.getFullYear() * 12 + date.getMonth()
}

const minDate = computed(() => parseDate(props.min))
const maxDate = computed(() => parseDate(props.max))
const minMonth = computed(() => (minDate.value ? monthKey(new Date(minDate.value.getFullYear(), minDate.value.getMonth(), 1)) : null))
const maxMonth = computed(() => (maxDate.value ? monthKey(new Date(maxDate.value.getFullYear(), maxDate.value.getMonth(), 1)) : null))
const selectedDates = computed(() => {
  const values = Array.isArray(props.modelValue) ? props.modelValue : [props.modelValue]
  return values.map(formatDate).filter(Boolean)
})
const selectedSet = computed(() => new Set(selectedDates.value))
const highlightedSet = computed(() => new Set(props.highlightedDates.map(formatDate).filter(Boolean)))
const todayText = formatDate(new Date())

function initialDisplayDate() {
  const today = parseDate(todayText)
  if (today && (!minDate.value || today >= minDate.value) && (!maxDate.value || today <= maxDate.value)) {
    return new Date(today.getFullYear(), today.getMonth(), 1)
  }
  const firstSelected = parseDate(selectedDates.value[0])
  if (firstSelected) return new Date(firstSelected.getFullYear(), firstSelected.getMonth(), 1)
  if (minDate.value) return new Date(minDate.value.getFullYear(), minDate.value.getMonth(), 1)
  return new Date(new Date().getFullYear(), new Date().getMonth(), 1)
}

const displayDate = ref(initialDisplayDate())

watch(
  () => [props.min, props.max],
  () => {
    const key = monthKey(displayDate.value)
    if (minMonth.value !== null && key < minMonth.value) displayDate.value = new Date(minDate.value.getFullYear(), minDate.value.getMonth(), 1)
    if (maxMonth.value !== null && key > maxMonth.value) displayDate.value = new Date(maxDate.value.getFullYear(), maxDate.value.getMonth(), 1)
  },
)

const canGoPrevious = computed(() => minMonth.value === null || monthKey(displayDate.value) > minMonth.value)
const canGoNext = computed(() => maxMonth.value === null || monthKey(displayDate.value) < maxMonth.value)
const currentMonthLabel = computed(() => `${displayDate.value.getFullYear()}年${monthNames[displayDate.value.getMonth()]}`)

const calendarDays = computed(() => {
  const year = displayDate.value.getFullYear()
  const month = displayDate.value.getMonth()
  const firstOfMonth = new Date(year, month, 1)
  const mondayFirstOffset = (firstOfMonth.getDay() + 6) % 7
  const start = new Date(year, month, 1 - mondayFirstOffset)
  const days = []

  for (let index = 0; index < 42; index += 1) {
    const date = new Date(start.getFullYear(), start.getMonth(), start.getDate() + index)
    const text = formatDate(date)
    const disabledByRange = Boolean((minDate.value && date < minDate.value) || (maxDate.value && date > maxDate.value))
    days.push({
      date,
      text,
      day: date.getDate(),
      isCurrentMonth: date.getMonth() === month,
      isOutsideMonth: date.getMonth() !== month,
      isWeekend: date.getDay() === 0 || date.getDay() === 6,
      isToday: text === todayText,
      isSelected: selectedSet.value.has(text),
      isHighlighted: highlightedSet.value.has(text),
      isDisabled: props.disabled || disabledByRange || date.getMonth() !== month,
    })
  }
  return days
})

function moveMonth(amount) {
  if (amount < 0 && !canGoPrevious.value) return
  if (amount > 0 && !canGoNext.value) return
  displayDate.value = addMonths(displayDate.value, amount)
}

function selectDate(day) {
  if (day.isDisabled || day.isOutsideMonth) return
  if (!props.multiple) {
    emit('update:modelValue', day.text)
    return
  }
  const next = new Set(selectedDates.value)
  if (next.has(day.text)) {
    next.delete(day.text)
  } else {
    next.add(day.text)
  }
  emit('update:modelValue', Array.from(next).sort())
}
</script>

<template>
  <div class="schedule-calendar">
    <div class="schedule-calendar-toolbar">
      <button type="button" class="calendar-nav-button" :disabled="!canGoPrevious" @click="moveMonth(-1)">
        <span aria-hidden="true">‹</span>
      </button>
      <strong>{{ currentMonthLabel }}</strong>
      <button type="button" class="calendar-nav-button" :disabled="!canGoNext" @click="moveMonth(1)">
        <span aria-hidden="true">›</span>
      </button>
    </div>
    <div class="schedule-calendar-weekdays">
      <span v-for="weekday in weekdayLabels" :key="weekday">{{ weekday }}</span>
    </div>
    <div class="schedule-calendar-grid">
      <button
        v-for="day in calendarDays"
        :key="day.text"
        type="button"
        class="schedule-calendar-day"
        :class="{
          'is-empty': day.isOutsideMonth,
          'is-weekend': day.isWeekend,
          'is-selected': day.isSelected,
          'is-highlighted': day.isHighlighted,
          'is-today': day.isToday,
        }"
        :disabled="day.isDisabled"
        @click="selectDate(day)"
      >
        <span v-if="day.isCurrentMonth">{{ day.day }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.schedule-calendar {
  width: 320px;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
  color: var(--text);
}

.schedule-calendar-toolbar {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) 34px;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
}

.schedule-calendar-toolbar strong {
  color: var(--strong);
  font-size: 14px;
  text-align: center;
}

.calendar-nav-button,
.schedule-calendar-day {
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: inherit;
  cursor: pointer;
  font: inherit;
}

.calendar-nav-button {
  width: 34px;
  height: 30px;
  color: var(--muted);
  font-size: 22px;
  line-height: 1;
}

.calendar-nav-button:hover:not(:disabled),
.schedule-calendar-day:hover:not(:disabled) {
  border-color: var(--line);
  background: var(--panel-soft);
}

.calendar-nav-button:disabled,
.schedule-calendar-day:disabled {
  cursor: default;
  opacity: 0.38;
}

.schedule-calendar-weekdays,
.schedule-calendar-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
}

.schedule-calendar-weekdays {
  margin-bottom: 6px;
  color: var(--muted);
  font-size: 12px;
  font-weight: 800;
  text-align: center;
}

.schedule-calendar-day {
  position: relative;
  width: 36px;
  height: 34px;
  justify-self: center;
  color: var(--text);
  font-size: 13px;
}

.schedule-calendar-day.is-weekend {
  color: #b45309;
}

.schedule-calendar-day.is-empty {
  visibility: hidden;
  pointer-events: none;
}

.schedule-calendar-day.is-selected {
  border-color: rgb(var(--v-theme-primary));
  background: rgb(var(--v-theme-primary));
  color: #fff;
  font-weight: 800;
}

.schedule-calendar-day.is-highlighted:not(.is-selected) {
  border-color: #d32f2f;
}

.schedule-calendar-day.is-today {
  box-shadow: 0 0 0 2px rgb(var(--v-theme-primary));
}
</style>
