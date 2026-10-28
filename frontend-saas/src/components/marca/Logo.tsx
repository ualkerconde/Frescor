import { useId } from "react"
import { cn } from "cn"

/*
 * Logo do Frescor (conceito da skill, ainda provisório): folha --primary
 * cuja nervura é um "certo" --accent, ao lado de "Frescor" em Sora 700.
 * A folha tem um degradê do verde-menta para o primário, para ganhar
 * volume. Sobre fundo claro o nome vai em --secondary (text-heading);
 * sobre fundo escuro (`sobreEscuro`, barra lateral e login) vai em branco.
 * O desenho é decorativo (aria-hidden); o nome em texto é o que o leitor
 * de tela lê.
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
  // O id do useId tem caracteres que quebram o url(#...) do SVG: só letras e números.
  const degrade = `folha-${useId().replace(/[^a-zA-Z0-9]/g, "")}`
  return (
    <span className={cn("inline-flex items-center gap-3", className)}>
      <svg width={tamanho} height={tamanho} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
        <defs>
          <linearGradient id={degrade} x1="27" y1="5" x2="6" y2="27" gradientUnits="userSpaceOnUse">
            <stop offset="0" stopColor="var(--fr-mint)" />
            <stop offset="0.45" stopColor="var(--fr-primary)" />
            <stop offset="1" stopColor="var(--fr-primary-hover)" />
          </linearGradient>
        </defs>
        <path d="M27 5C14 5 5 12 5 22c0 2 .5 3.5 1.2 5C8 26 10 25 12 25c10 0 15-9 15-20z" fill={`url(#${degrade})`} />
        <path
          d="M10 18.5l4 4 8-9"
          fill="none"
          stroke="var(--fr-accent)"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span
        className={cn(
          "font-heading text-[28px] leading-none font-bold tracking-[-0.03em]",
          sobreEscuro ? "text-white" : "text-heading",
        )}
      >
        Frescor
      </span>
    </span>
  )
}
