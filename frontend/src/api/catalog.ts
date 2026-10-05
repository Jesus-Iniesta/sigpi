import { apiFetch } from '@/api/client'
import type {
  Category,
  CategoryInput,
  OrganizationalUnit,
  ServiceArea,
  ServiceAreaInput,
  Shift,
  ShiftInput,
  Specialty,
  SpecialtyInput,
  Technician,
  TechnicianUpdate,
} from '@/api/types'

export type {
  Category,
  CategoryInput,
  OrganizationalUnit,
  ServiceArea,
  ServiceAreaInput,
  Shift,
  ShiftInput,
  Specialty,
  SpecialtyInput,
  Technician,
  TechnicianUpdate,
}

export const getAreas = () => apiFetch<ServiceArea[]>('/catalog/areas')

export const getOrganizationalUnits = () =>
  apiFetch<OrganizationalUnit[]>('/catalog/organizational-units')

export const getCategories = () => apiFetch<Category[]>('/catalog/categories')

export const getCategoriesByArea = (areaId: string) =>
  apiFetch<Category[]>(
    `/catalog/categories?area_id=${encodeURIComponent(areaId)}`,
  )

export const getSpecialties = () =>
  apiFetch<Specialty[]>('/catalog/specialties')

export const getSpecialtiesByCategory = (categoryId: string) =>
  apiFetch<Specialty[]>(
    `/catalog/specialties?category_id=${encodeURIComponent(categoryId)}`,
  )

export const getShifts = () => apiFetch<Shift[]>('/catalog/shifts')

export const getTechnicians = () =>
  apiFetch<Technician[]>('/catalog/technicians')

export const getTechniciansBySpecialty = (specialtyId: string) =>
  apiFetch<Technician[]>(
    `/catalog/technicians?specialty_id=${encodeURIComponent(specialtyId)}`,
  )

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
