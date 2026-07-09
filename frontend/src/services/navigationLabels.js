import { t } from './pipecloudState'

const moduleTitleKeys = {
  initialization: 'initializationData',
  arrival: 'arrivalManagement',
  antiCorrosion: 'antiCorrosionManagementScheduling',
  cutting: 'cuttingManagementScheduling',
  welding: 'weldingManagementScheduling',
  schedule: 'totalSchedulingPlan',
}

const moduleDescriptionKeys = {
  initialization: 'initializationModuleDescription',
  arrival: 'arrivalModuleDescription',
  antiCorrosion: 'antiCorrosionModuleDescription',
  cutting: 'cuttingModuleDescription',
  welding: 'weldingModuleDescription',
  schedule: 'scheduleModuleDescription',
}

const actionNameKeys = {
  'prefab-weld-library': 'actionPrefabWeldLibrary',
  'arrival-library': 'actionArrivalLibrary',
  'update-weld-arrival-status': 'actionUpdateWeldArrivalStatus',
  'anti-corrosion-pre-schedule': 'actionAntiCorrosionPreSchedule',
  'anti-corrosion-schedule': 'actionAntiCorrosionSchedule',
  'auto-weld-schedule': 'actionAutoWeldSchedule',
  'weld-pre-schedule': 'actionWeldPreSchedule',
  'confirm-cutting-pre-schedule': 'actionConfirmCuttingPreSchedule',
  'future-schedule': 'actionFutureSchedule',
}

const libraryTitleKeys = {
  'weld-library': 'weldLibrary',
  'pipe-library': 'pipeLibrary',
  'fitting-library': 'fittingLibrary',
  'anti-pipe-library': 'antiCorrosionPipeLibrary',
  'anti-fitting-library': 'antiCorrosionFittingLibrary',
  'anti-corrosion-commission-library': 'antiCorrosionCommissionLibrary',
  'master-schedule-library': 'masterScheduleLibrary',
}

export function localizedModuleTitle(module) {
  const titleKey = moduleTitleKeys[module?.key]
  if (titleKey) return t(titleKey)
  return module?.name === '初始化预制' ? t('initializationData') : module?.name
}

export function localizedModuleDescription(module) {
  const descriptionKey = moduleDescriptionKeys[module?.key]
  return descriptionKey ? t(descriptionKey) : module?.description
}

export function localizedActionName(action) {
  const nameKey = actionNameKeys[action?.key]
  return nameKey ? t(nameKey) : action?.name
}

export function localizedLibraryTitle(library) {
  const titleKey = libraryTitleKeys[library?.key]
  return titleKey ? t(titleKey) : library?.name
}
