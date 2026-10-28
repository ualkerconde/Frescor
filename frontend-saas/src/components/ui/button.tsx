import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"
import { Loader2 } from "lucide-react"
import { Slot } from "radix-ui"

/*
 * Botão do shadcn ajustado à skill Frescor:
 * - altura mínima 44px (área de toque), texto 16px 600, raio 10px;
 * - primário (default): fundo --primary, texto branco, hover --primary-hover;
 * - secundário (secondary): borda 2px --primary, texto --primary, fundo transparente;
 * - perigo (destructive): fundo --error, texto branco;
 * - foco visível: anel de 2px --primary com 2px de afastamento;
 * - `carregando`: spinner + texto (ex.: "Enviando…") e clique bloqueado.
 * Ícones lucide em 20px. Rótulo sempre um verbo ("Importar vendas").
 */
const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 rounded-lg border border-transparent text-base font-semibold whitespace-nowrap transition-colors duration-150 select-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary disabled:pointer-events-none disabled:opacity-60 aria-invalid:border-error [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-5",
  {
    variants: {
      variant: {
        // Cor lisa e um traço de sombra; sem degradê nem brilho.
        default: "bg-primary text-primary-foreground shadow-[0_1px_2px_rgb(21_33_43/0.12)] hover:bg-primary-hover",
        secondary: "border-2 border-primary bg-transparent text-primary hover:bg-surface",
        destructive: "bg-error text-white shadow-[0_1px_2px_rgb(21_33_43/0.12)] hover:bg-error/90",
        outline: "border-input-border bg-card text-foreground hover:bg-surface",
        ghost: "text-foreground hover:bg-surface",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-11 px-4",
        sm: "h-11 px-3 text-sm",
        lg: "h-12 px-6",
        icon: "size-11",
        "icon-sm": "size-11",
        "icon-lg": "size-12",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

type ButtonProps = React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean
    /** Mostra o spinner com `textoCarregando` e bloqueia o clique. */
    carregando?: boolean
    textoCarregando?: string
  }

function Button({
  className,
  variant = "default",
  size = "default",
  asChild = false,
  carregando = false,
  textoCarregando,
  disabled,
  children,
  ...props
}: ButtonProps) {
  const Comp = asChild ? Slot.Root : "button"

  return (
    <Comp
      data-slot="button"
      data-variant={variant}
      data-size={size}
      className={cn(buttonVariants({ variant, size, className }))}
      disabled={disabled || carregando}
      aria-busy={carregando || undefined}
      {...props}
    >
      {/* Com asChild o Slot exige um único filho: o spinner só entra no botão comum. */}
      {carregando && !asChild ? (
        <>
          <Loader2 className="animate-spin" aria-hidden="true" />
          {textoCarregando ?? children}
        </>
      ) : (
        children
      )}
    </Comp>
  )
}

export { Button, buttonVariants }
