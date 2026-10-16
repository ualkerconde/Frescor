import * as React from "react"
import { cn } from "cn"

/*
 * Textarea do shadcn ajustado à skill Frescor (usado a partir do N9), igual
 * ao Input: borda --input-border (3:1), fundo branco, texto 16px, foco
 * visível de 2px --primary com 2px de afastamento, erro com borda --error.
 */
function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  return (
    <textarea
      data-slot="textarea"
      className={cn(
        "flex field-sizing-content min-h-16 w-full rounded-lg border border-input-border bg-card px-3 py-2 text-base text-foreground transition-colors placeholder:text-muted-foreground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:cursor-not-allowed disabled:bg-surface disabled:opacity-60 aria-invalid:border-2 aria-invalid:border-error",
        className
      )}
      {...props}
    />
  )
}

export { Textarea }
