/*
 * Cabeçalho do conteúdo de uma tela (padrão de 11/11/2026): sobretítulo
 * curto em maiúsculas com um traço dourado à esquerda, título (h1) em Sora,
 * uma linha de apoio e, à direita, as ações da tela (no máximo um botão
 * primário, skill: uma ação principal por tela).
 */
import type { ReactNode } from "react"

export function CabecalhoPagina({
  sobretitulo,
  titulo,
  descricao,
  acoes,
}: {
  sobretitulo?: ReactNode
  titulo: ReactNode
  descricao?: ReactNode
  acoes?: ReactNode
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-4">
      <div className="min-w-0">
        {sobretitulo && (
          <p className="mb-2 flex items-center gap-2.5 text-xs font-semibold tracking-[0.08em] text-muted-foreground uppercase">
            <span aria-hidden="true" className="h-0.5 w-5 rounded-full bg-highlight" />
            {sobretitulo}
          </p>
        )}
        <h1 className="text-[30px] leading-tight font-bold tracking-[-0.02em]">{titulo}</h1>
        {descricao && <p className="mt-2 max-w-2xl text-muted-foreground">{descricao}</p>}
      </div>
      {acoes && <div className="flex flex-wrap items-center gap-3">{acoes}</div>}
    </div>
  )
}
