import type { components } from './openapi'

export type ApiSchemas = components['schemas']
export type UserRole = ApiSchemas['RoleName']
export type User = Omit<ApiSchemas['UserRead'], 'roles'> & {
  roles: UserRole[]
}
// openapi.ts aún no incluye `password` en UserCreate; se agrega aquí hasta regenerarlo.
export type CreateUserInput = ApiSchemas['UserCreate'] & { password: string }
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
export type CatalogOptions = ApiSchemas['CatalogOptionsRead']
export type ShiftOption = ApiSchemas['ShiftOptionRead']
export type Request = ApiSchemas['RequestRead']
export type CreateRequestInput = ApiSchemas['RequestCreate']
export type AssistedChannel = 'phone' | 'in_person'
export type CreateAssistedRequestInput = Omit<CreateRequestInput, 'channel'> & {
  channel: AssistedChannel
}
export type Priority = ApiSchemas['Priority']
/*
 * Clasificación automática que acompaña al detalle de una solicitud (S4-13, HU-02.1 AC2).
 * `openapi.ts` todavía no incluye estos campos de RequestRead; se agregan aquí.
 */
export type RequestClassification = {
  proposed_category_id: string | null
  proposed_category_name: string | null
  classification_confidence: number | null
  model_version: string | null
}
export type WaitReason = 'external_input' | 'user_information'
export type SlaAgreement = ApiSchemas['SlaAgreementRead']
export type CreateSlaAgreementInput = ApiSchemas['SlaAgreementCreate']
export type SlaVersion = ApiSchemas['SlaVersionRead']
export type CreateSlaVersionInput = ApiSchemas['SlaVersionCreate']
export type EffectiveSla = ApiSchemas['EffectiveSlaRead']
export type HealthResponse = {
  status: string
  service: string
}
