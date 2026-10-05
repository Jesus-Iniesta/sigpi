import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getCategories } from '@/api/catalog'
import {
  createSlaAgreement,
  getEffectiveSla,
  getSlaAgreements,
  getSlaVersions,
  publishSlaVersion,
  type SlaVersionInput,
} from '@/api/sla'

export function useSlaAgreements() {
  return useQuery({
    queryKey: ['sla', 'agreements'],
    queryFn: getSlaAgreements,
  })
}

export function useSlaCategories() {
  return useQuery({ queryKey: ['sla', 'categories'], queryFn: getCategories })
}

export function useSlaVersions(agreementId: string | undefined) {
  return useQuery({
    queryKey: ['sla', 'versions', agreementId],
    queryFn: () => getSlaVersions(agreementId as string),
    enabled: Boolean(agreementId),
  })
}

export function useCreateSlaAgreement() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: createSlaAgreement,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ['sla', 'agreements'] }),
  })
}

export function usePublishSlaVersion(agreementId: string | undefined) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (input: SlaVersionInput) =>
      publishSlaVersion(agreementId as string, input),
    onSuccess: () =>
      queryClient.invalidateQueries({
        queryKey: ['sla', 'versions', agreementId],
      }),
  })
}

export function useEffectiveSlaLookup() {
  return useMutation({ mutationFn: getEffectiveSla })
}
