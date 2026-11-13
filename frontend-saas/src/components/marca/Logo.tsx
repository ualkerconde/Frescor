import { cn } from "cn"

/*
 * Logo do Frescor no visual "Comando" (D117, 13/11/2026): selo quadrado em
 * âmbar (--primary) com a folha na tinta escura (--on-color) e a nervura em
 * "certo" no próprio âmbar, ao lado de "Frescor" em Inter Tight 700.
 *
 * `comNome = false` mostra só o selo (barra lateral de ícones); o nome
 * continua para o leitor de tela (sr-only). O desenho é decorativo
 * (aria-hidden).
 */
export function Selo({ tamanho = 40, className }: { tamanho?: number; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn("grid shrink-0 place-items-center rounded-[30%] bg-primary", className)}
      style={{ width: tamanho, height: tamanho }}
    >
      <svg width={tamanho * 0.55} height={tamanho * 0.55} viewBox="0 0 24 24" focusable="false">
        <path d="M5 19c0-9 6-14 15-14-1 9-6 15-15 14z" fill="var(--fr-on-color)" />
        <path
          d="M8 13l3 3 5-6"
          fill="none"
          stroke="var(--fr-primary)"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  )
}

export function Logo({
  className,
  tamanho = 40,
  comNome = true,
}: {
  className?: string
  tamanho?: number
  comNome?: boolean
}) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <Selo tamanho={tamanho} />
      <span
        className={cn(
          "font-heading text-[26px] leading-none font-bold tracking-[-0.03em] text-heading",
          !comNome && "sr-only",
        )}
      >
        Frescor
      </span>
    </span>
  )
}
