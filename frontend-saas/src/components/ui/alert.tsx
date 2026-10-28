import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"

/*
 * Alerta do shadcn ajustado à skill Frescor: fundo *-bg, texto e ícone na
 * cor semântica, raio 10px. Conteúdo: uma frase do que houve (AlertTitle) e
 * uma do que fazer (AlertDescription). Cor nunca sozinha: sempre com ícone.
 * Contrastes (skill): erro 5,75 · atenção 4,9 · sucesso 4,75 (todos AA).
 */
const alertVariants = cva(
  "group/alert relative grid w-full gap-0.5 rounded-lg px-4 py-3 text-left ring-1 ring-current/15 ring-inset text-base has-[>svg]:grid-cols-[auto_1fr] has-[>svg]:gap-x-3 *:[svg]:row-span-2 *:[svg]:translate-y-0.5 *:[svg]:text-current *:[svg:not([class*='size-'])]:size-5",
  {
    variants: {
      variant: {
        info: "bg-surface text-foreground",
        erro: "bg-error-bg text-error",
        aviso: "bg-warning-bg text-warning",
        sucesso: "bg-success-bg text-success",
      },
    },
    defaultVariants: {
      variant: "info",
    },
  }
)

function Alert({
  className,
  variant,
  ...props
}: React.ComponentProps<"div"> & VariantProps<typeof alertVariants>) {
  return (
    <div
      data-slot="alert"
      role="alert"
      className={cn(alertVariants({ variant }), className)}
      {...props}
    />
  )
}

function AlertTitle({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="alert-title"
      className={cn(
        "font-semibold group-has-[>svg]/alert:col-start-2 [&_a]:underline [&_a]:underline-offset-3",
        className
      )}
      {...props}
    />
  )
}

function AlertDescription({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="alert-description"
      className={cn(
        "text-sm text-current group-has-[>svg]/alert:col-start-2 [&_a]:underline [&_a]:underline-offset-3 [&_p:not(:last-child)]:mb-2",
        className
      )}
      {...props}
    />
  )
}

export { Alert, AlertTitle, AlertDescription }
