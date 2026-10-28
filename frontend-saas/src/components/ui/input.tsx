import * as React from "react"
import { cn } from "cn"

/*
 * Input do shadcn ajustado à skill Frescor: 44px de altura, borda 1px
 * --input-border (contraste 3:1 exigido para borda de controle), fundo
 * branco, texto 16px, foco visível de 2px --primary e borda --error quando
 * aria-invalid. O label fica sempre visível acima (nunca só placeholder).
 */
function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      data-slot="input"
      className={cn(
        "h-11 w-full min-w-0 rounded-lg border border-input-border bg-card px-3 text-base text-foreground shadow-[inset_0_1px_2px_rgb(21_33_43/0.06)] transition-colors hover:border-heading placeholder:text-muted-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:cursor-not-allowed disabled:bg-surface disabled:opacity-60 aria-invalid:border-2 aria-invalid:border-error",
        className
      )}
      {...props}
    />
  )
}

export { Input }
