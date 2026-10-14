/*
 * Etiqueta de status (skill Frescor: pill 14px 600, fundo *-bg e texto na
 * cor semântica; --accent só como fundo, com texto --text). Sempre com
 * ícone e texto: a cor nunca aparece sozinha.
 */
import { CalendarClock, CircleHelp, Sprout } from "lucide-react"
import { cn } from "cn"

const TIPOS = {
  evento: { classe: "bg-highlight text-foreground", Icone: CalendarClock },
  pouco_historico: { classe: "bg-warning-bg text-warning", Icone: Sprout },
  sem_previsao: { classe: "bg-error-bg text-error", Icone: CircleHelp },
} as const

export function Etiqueta({ tipo, children }: { tipo: keyof typeof TIPOS; children: React.ReactNode }) {
  const { classe, Icone } = TIPOS[tipo]
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-sm font-semibold whitespace-nowrap", classe)}>
      <Icone className="size-4" aria-hidden="true" />
      {children}
    </span>
  )
}
