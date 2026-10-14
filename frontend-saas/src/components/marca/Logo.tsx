import { cn } from "cn"

/*
 * Logo do Frescor (conceito da skill, ainda provisório): folha --primary
 * cuja nervura é um "certo" --accent, ao lado de "Frescor" em Sora 700
 * --secondary (utilitário text-heading). O desenho é decorativo
 * (aria-hidden); o nome em texto é o que o leitor de tela lê.
 */
export function Logo({ className, tamanho = 40 }: { className?: string; tamanho?: number }) {
  return (
    <span className={cn("inline-flex items-center gap-3", className)}>
      <svg width={tamanho} height={tamanho} viewBox="0 0 32 32" aria-hidden="true" focusable="false">
        <path
          d="M27 5C14 5 5 12 5 22c0 2 .5 3.5 1.2 5C8 26 10 25 12 25c10 0 15-9 15-20z"
          fill="var(--fr-primary)"
        />
        <path
          d="M10 18.5l4 4 8-9"
          fill="none"
          stroke="var(--fr-accent)"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span className="font-heading text-[28px] leading-none font-bold text-heading">Frescor</span>
    </span>
  )
}
