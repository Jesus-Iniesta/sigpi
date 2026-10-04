import { apiFetch } from '@/api/client'

export type ServiceArea = {
  id: string
  unit_id: string
  name: string
  description: string | null
  is_active: boolean
}

export type Category = {
  id: string
  area_id: string
  name: string
  description: string | null
  is_active: boolean
}

export type Specialty = {
  id: string
  category_id: string
  name: string
  is_active: boolean
}

export type Shift = {
  id: string
  name: string
  start_minute: number
  end_minute: number
  is_active: boolean
}

export type Technician = {
  id: string
  full_name: string
  support_level: 'level_1' | 'level_2' | null
  shift_id: string | null
  max_load: number | null
  is_active: boolean
  specialty_ids: string[]
}

export type TechnicianUpdate = {
  support_level?: Technician['support_level']
  shift_id?: string | null
  max_load?: number | null
  specialty_ids?: string[]
}

export type ServiceAreaInput = {
  unit_id: string
  name: string
  description?: string | null
}

export type CategoryInput = {
  area_id: string
  name: string
  description?: string | null
}

export type SpecialtyInput = {
  category_id: string
  name: string
}

export type ShiftInput = {
  name: string
  start_minute: number
  end_minute: number
}

export const getAreas = () => apiFetch<ServiceArea[]>('/catalog/areas')

export const getCategories = () => apiFetch<Category[]>('/catalog/categories')

export const getSpecialties = () => apiFetch<Specialty[]>('/catalog/specialties')

export const getShifts = () => apiFetch<Shift[]>('/catalog/shifts')

export const getTechnicians = () => apiFetch<Technician[]>('/catalog/technicians')

export const createArea = (input: ServiceAreaInput) =>
  apiFetch<ServiceArea>('/catalog/areas', {
    method: 'POST',
    body: JSON.stringify(input),
  })

export const createCategory = (input: CategoryInput) =>
  apiFetch<Category>('/catalog/categories', {
    method: 'POST',
    body: JSON.stringify(input),
  })

export const createSpecialty = (input: SpecialtyInput) =>
  apiFetch<Specialty>('/catalog/specialties', {
    method: 'POST',
    body: JSON.stringify(input),
  })

export const createShift = (input: ShiftInput) =>
  apiFetch<Shift>('/catalog/shifts', {
    method: 'POST',
    body: JSON.stringify(input),
  })

export const updateTechnician = (userId: string, input: TechnicianUpdate) =>
  apiFetch<Technician>(`/catalog/technicians/${userId}`, {
    method: 'PATCH',
    body: JSON.stringify(input),
  })
