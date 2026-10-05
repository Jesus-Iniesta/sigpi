import type { components } from './openapi'

export type ApiSchemas = components['schemas']
export type UserRole = ApiSchemas['RoleName']
export type User = Omit<ApiSchemas['UserRead'], 'roles'> & {
  roles: UserRole[]
}
export type CreateUserInput = ApiSchemas['UserCreate']
export type UpdateUserInput = ApiSchemas['UserUpdate']
export type ServiceArea = ApiSchemas['ServiceAreaRead']
export type OrganizationalUnit = ApiSchemas['OrganizationalUnitRead']
export type Category = ApiSchemas['CategoryRead']
export type Specialty = ApiSchemas['SpecialtyRead']
export type Shift = ApiSchemas['ShiftRead']
export type Technician = ApiSchemas['TechnicianRead']
export type TechnicianUpdate = ApiSchemas['TechnicianProfileUpdate']
export type ServiceAreaInput = ApiSchemas['ServiceAreaCreate']
export type CategoryInput = ApiSchemas['CategoryCreate']
export type SpecialtyInput = ApiSchemas['SpecialtyCreate']
export type ShiftInput = ApiSchemas['ShiftCreate']
export type Request = ApiSchemas['RequestRead']
export type CreateRequestInput = ApiSchemas['RequestCreate']
export type Priority = ApiSchemas['Priority']
export type SlaAgreement = ApiSchemas['SlaAgreementRead']
export type CreateSlaAgreementInput = ApiSchemas['SlaAgreementCreate']
export type SlaVersion = ApiSchemas['SlaVersionRead']
export type CreateSlaVersionInput = ApiSchemas['SlaVersionCreate']
export type EffectiveSla = ApiSchemas['EffectiveSlaRead']
export type HealthResponse = {
  status: string
  service: string
}
