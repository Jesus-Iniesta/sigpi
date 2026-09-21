import type { ButtonHTMLAttributes } from 'react'
import { cn } from '@/shared/lib/utils'

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: 'primary' | 'secondary' | 'ghost'
}

export function Button({
  className,
  variant = 'primary',
  ...props
}: ButtonProps) {
  return (
    <button
      className={cn(
        'inline-flex min-h-10 items-center justify-center gap-2 rounded-lg px-4 text-sm font-semibold transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#0f766e] disabled:pointer-events-none disabled:opacity-50',
        variant === 'primary' && 'bg-[#0f766e] text-white hover:bg-[#115e59]',
        variant === 'secondary' &&
          'border border-[#d7e0df] bg-white text-[#334155] hover:bg-[#eef5f4]',
        variant === 'ghost' &&
          'text-[#52616b] hover:bg-[#e7efee] hover:text-[#17212b]',
        className,
      )}
      {...props}
    />
  )
}
