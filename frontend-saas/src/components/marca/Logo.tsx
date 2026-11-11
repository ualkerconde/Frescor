import { cn } from "cn"

/*
 * Logo do Frescor (conceito da skill, ainda provisório): folha --primary
 * cuja nervura é um "certo" --accent, ao lado de "Frescor" em Sora 700.
 * Sobre fundo claro o nome vai em --secondary (text-heading); sobre a
 * barra lateral escura (`sobreEscuro`) vai em branco. O desenho é
 * decorativo (aria-hidden); o nome em texto é o que o leitor de tela lê.
 */
export function Logo({
  className,
  tamanho = 40,
  sobreEscuro = false,
}: {
  className?: string
  tamanho?: number
  sobreEscuro?: boolean
}) {
  return (
    <span className={cn("inline-flex items-center gap-2.5", className)}>
      <svg width={tamanho} height={tamanho} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
        <path
          d="M27 5C14 5 5 12 5 22c0 2 .5 3.5 1.2 5C8 26 10 25 12 25c10 0 15-9 15-20z"
          fill={sobreEscuro ? "#ffffff" : "var(--fr-primary)"}
        />
        <path
          d="M10 18.5l4 4 8-9"
          fill="none"
          stroke={sobreEscuro ? "var(--fr-secondary)" : "var(--fr-accent)"}
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span
        className={cn(
          "font-heading text-[28px] leading-none font-bold tracking-[-0.02em]",
          sobreEscuro ? "text-white" : "text-heading",
        )}
      >
        Frescor
      </span>
    </span>
  )
}
