import { postJson, requestJson } from './http'

function csrfToken() {
  const item = document.cookie
    .split('; ')
    .find((cookie) => cookie.startsWith('csrftoken='))
  return item ? decodeURIComponent(item.slice('csrftoken='.length)) : ''
}

export async function runPlanRollover() {
  await requestJson('/developer/plan-rollover/')
  return postJson('/developer/plan-rollover/', {}, {
    headers: { 'X-CSRFToken': csrfToken() },
  })
}

export async function fetchDatabaseOverview() {
  return requestJson('/developer/database/')
}

export async function clearDatabase(tables = []) {
  await requestJson('/developer/database/')
  return postJson('/developer/database/clear/', { tables }, {
    headers: { 'X-CSRFToken': csrfToken() },
  })
}
