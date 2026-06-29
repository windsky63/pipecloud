import { computed } from 'vue'
import { uiTheme } from './pipecloudState'

export const isDarkVTableTheme = computed(() => uiTheme.value === 'pipecloudDark')
export const vTableThemeKey = computed(() => uiTheme.value)

const lightPalette = {
  underlay: '#f8fafc',
  headerBg: '#edf3fb',
  headerText: '#1f2a3d',
  bodyBg: '#ffffff',
  bodyAltBg: '#f8fafc',
  bodyText: '#233044',
  mutedText: '#64748b',
  line: '#d9e3f0',
  bodyLine: '#e7edf5',
  frameLine: '#d7e0ec',
  selectedBorder: '#2563eb',
  selectedBg: 'rgba(37, 99, 235, .08)',
  selectedRowBg: 'rgba(37, 99, 235, .05)',
  hoverBg: '#eef6ff',
  hoverRowBg: '#f4f8ff',
  scrollbarRail: '#eef2f7',
  scrollbarThumb: '#b8c5d8',
  cutFill: '#f6c400',
  remainingFill: '#b9c3d8',
  segmentStroke: '#ffffff',
  segmentText: '#172033',
}

const darkPalette = {
  underlay: '#111827',
  headerBg: '#1f2937',
  headerText: '#f3f4f6',
  bodyBg: '#172033',
  bodyAltBg: '#111827',
  bodyText: '#e5e7eb',
  mutedText: '#9ca3af',
  line: '#374151',
  bodyLine: '#293548',
  frameLine: '#374151',
  selectedBorder: '#60a5fa',
  selectedBg: 'rgba(96, 165, 250, .14)',
  selectedRowBg: 'rgba(96, 165, 250, .09)',
  hoverBg: '#273142',
  hoverRowBg: '#202b3a',
  scrollbarRail: '#1f2937',
  scrollbarThumb: '#4b5563',
  cutFill: '#eab308',
  remainingFill: '#475569',
  segmentStroke: '#1f2937',
  segmentText: '#f8fafc',
}

const grayPalette = {
  underlay: '#dfe5ea',
  headerBg: '#d3dbe3',
  headerText: '#202a35',
  bodyBg: '#eef1f4',
  bodyAltBg: '#e7ebef',
  bodyText: '#27313d',
  mutedText: '#64717e',
  line: '#c4ced8',
  bodyLine: '#d2dae2',
  frameLine: '#c4ced8',
  selectedBorder: '#3f6b8f',
  selectedBg: 'rgba(63, 107, 143, .12)',
  selectedRowBg: 'rgba(63, 107, 143, .08)',
  hoverBg: '#dce7ef',
  hoverRowBg: '#e1e8ee',
  scrollbarRail: '#d5dde5',
  scrollbarThumb: '#93a3b3',
  cutFill: '#d9b64c',
  remainingFill: '#9aa8b8',
  segmentStroke: '#eef1f4',
  segmentText: '#202a35',
}

export function getVTablePalette() {
  if (uiTheme.value === 'pipecloudDark') return darkPalette
  if (uiTheme.value === 'pipecloudGray') return grayPalette
  return lightPalette
}

export function getBasicVTableTheme({ striped = true, rowHeader = false } = {}) {
  const palette = getVTablePalette()
  return {
    underlayBackgroundColor: palette.underlay,
    defaultStyle: {
      bgColor: ({ row }) => (striped && row > 0 && row % 2 === 0 ? palette.bodyBg : palette.bodyAltBg),
      color: palette.bodyText,
      fontSize: 13,
      borderColor: [null, null, palette.bodyLine, null],
      borderLineWidth: [0, 0, 1, 0],
      padding: [0, 12, 0, 12],
      hover: {
        cellBgColor: palette.hoverBg,
        inlineRowBgColor: palette.hoverRowBg,
        inlineColumnBgColor: palette.hoverRowBg,
      },
    },
    headerStyle: {
      bgColor: palette.headerBg,
      color: palette.headerText,
      fontSize: 13,
      fontWeight: 700,
      borderColor: [null, null, palette.line, null],
      borderLineWidth: [0, 0, 1, 0],
      padding: [0, 12, 0, 12],
    },
    ...(rowHeader
      ? {
          rowHeaderStyle: {
            bgColor: palette.headerBg,
            color: palette.mutedText,
            borderColor: [null, null, palette.bodyLine, null],
            borderLineWidth: [0, 0, 1, 0],
          },
        }
      : {}),
    frameStyle: {
      borderColor: palette.frameLine,
      borderLineWidth: 0,
    },
    selectionStyle: {
      cellBorderColor: palette.selectedBorder,
      cellBorderLineWidth: 2,
      cellBgColor: palette.selectedBg,
      inlineRowBgColor: palette.selectedRowBg,
      inlineColumnBgColor: palette.selectedRowBg,
    },
    scrollStyle: {
      visible: 'always',
      barToSide: true,
      width: 10,
      scrollRailColor: palette.scrollbarRail,
      scrollSliderColor: palette.scrollbarThumb,
      scrollSliderCornerRadius: 6,
    },
  }
}
