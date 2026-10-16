import type { components } from './schema'

export type HealthResponse = components['schemas']['HealthResponse']

const API_BASE = '/api'

export async function getHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE}/health`)
  if (!response.ok) {
    throw new Error(`Health check failed: ${response.status}`)
  }
  return response.json()
}
