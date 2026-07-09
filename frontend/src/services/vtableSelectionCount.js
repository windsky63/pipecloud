import { t } from './pipecloudState'

function normalizedRange(range) {
  if (!range?.start || !range?.end) return null
  return {
    startCol: Math.min(range.start.col, range.end.col),
    endCol: Math.max(range.start.col, range.end.col),
    startRow: Math.min(range.start.row, range.end.row),
    endRow: Math.max(range.start.row, range.end.row),
  }
}

function selectedWholeColumn(table, event) {
  const headerRows = Math.max(Number(table?.columnHeaderLevelCount) || 1, 1)
  const lastRow = Math.max(Number(table?.rowCount) - 1, headerRows - 1)
  const ranges = (event?.ranges || table?.getSelectedCellRanges?.() || [])
    .map(normalizedRange)
    .filter(Boolean)
  const range = ranges.find((item) => (
    item.startCol === item.endCol
    && item.startRow < headerRows
    && item.endRow >= lastRow
  ))
  if (range) return range.startCol
  if (Number(event?.row) < headerRows && Number.isInteger(event?.col)) return event.col
  return null
}

function numericValue(value) {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  const text = String(value ?? '').trim()
  if (!text) return null
  const normalized = text.replaceAll(',', '')
  if (!/^[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i.test(normalized)) return null
  const number = Number(normalized)
  return Number.isFinite(number) ? number : null
}

function columnStats(table, columnIndex) {
  const headerRows = Math.max(Number(table?.columnHeaderLevelCount) || 1, 1)
  const rowCount = Number(table?.rowCount) || 0
  let count = 0
  let sum = 0
  let allNumeric = true
  for (let row = headerRows; row < rowCount; row += 1) {
    const value = table.getCellValue?.(columnIndex, row)
    if (value === null || value === undefined || String(value).trim() === '') continue
    count += 1
    const number = numericValue(value)
    if (number === null) allNumeric = false
    else sum += number
  }
  return { count, isNumeric: count > 0 && allNumeric, sum }
}

export function createVTableSelectionLayout(host) {
  if (!host) return null
  host.replaceChildren()
  host.style.display = 'flex'
  host.style.flexDirection = 'column'
  host.style.minHeight = '0'

  const viewport = document.createElement('div')
  Object.assign(viewport.style, {
    position: 'relative',
    flex: '1 1 auto',
    width: '100%',
    minHeight: '0',
    overflow: 'hidden',
  })

  const footer = document.createElement('div')
  Object.assign(footer.style, {
    display: 'flex',
    flex: '0 0 34px',
    alignItems: 'center',
    height: '34px',
    padding: '0 12px',
    overflow: 'hidden',
    borderTop: '1px solid var(--line)',
    background: 'var(--panel-soft)',
    color: 'var(--muted)',
    fontSize: '12px',
    fontWeight: '600',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  })
  host.append(viewport, footer)
  return {
    viewport,
    footer,
    destroy() {
      host.replaceChildren()
      host.style.removeProperty('display')
      host.style.removeProperty('flex-direction')
      host.style.removeProperty('min-height')
    },
  }
}

export function attachVTableColumnSelectionCount(table, layout) {
  if (!table || !layout?.footer) return () => {}

  const hide = () => {
    layout.footer.textContent = ''
    layout.footer.removeAttribute('title')
  }
  const show = (event) => {
    const columnIndex = selectedWholeColumn(table, event)
    if (columnIndex === null) {
      hide()
      return
    }
    const headerRow = Math.max((Number(table.columnHeaderLevelCount) || 1) - 1, 0)
    const column = String(table.getCellValue?.(columnIndex, headerRow) ?? '') || '-'
    const stats = columnStats(table, columnIndex)
    const text = stats.isNumeric
      ? t('selectedNumericColumnStats', {
          column,
          count: stats.count,
          sum: new Intl.NumberFormat(undefined, { maximumFractionDigits: 6 }).format(stats.sum),
        })
      : t('selectedStringColumnStats', {
          column,
          count: stats.count,
        })
    layout.footer.textContent = text
    layout.footer.title = text
  }

  table.on(table.constructor.EVENT_TYPE.SELECTED_CELL, show)
  table.on(table.constructor.EVENT_TYPE.SELECTED_CLEAR, hide)

  return () => {
    hide()
    layout.destroy()
  }
}
