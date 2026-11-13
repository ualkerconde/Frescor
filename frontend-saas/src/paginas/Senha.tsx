/*
 * Trocar a própria senha (gestor). POST /auth/web/senha.
 *
 * Por que existe: o gestor recebe uma senha provisória na implantação
 * (scripts/implantar_cliente.py). Regras iguais às do backend
 * (app/services/senha_service.py): senha atual obrigatória; nova com pelo
 * menos 8 caracteres e diferente da atual. A tela confere o básico antes de
 * enviar; o resto (ex.: senha atual errada) vem do backend em `detail`.
 * Fora do menu: abre pelo rodapé da barra lateral e pela busca de telas.
 */
import { useState, type FormEvent } from "react"
import { useMutation } from "@tanstack/react-query"
import { CircleAlert } from "lucide-react"
import { toast } from "sonner"
import { CabecalhoPagina } from "@/components/layout/CabecalhoPagina"
import { Alert, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Toaster } from "@/components/ui/sonner"
import { ErroApi, apiJson } from "@/lib/api/cliente"

export const TAMANHO_MINIMO = 8

interface Campos {
  atual: string
  nova: string
  repetir: string
}

export function errosDaSenha({ atual, nova, repetir }: Campos): Partial<Record<keyof Campos, string>> {
  const erros: Partial<Record<keyof Campos, string>> = {}
  if (!atual) erros.atual = "Digite a senha atual."
  if (nova.trim() === "") erros.nova = "Digite a senha nova."
  else if (nova.length < TAMANHO_MINIMO) erros.nova = `A senha nova precisa ter pelo menos ${TAMANHO_MINIMO} caracteres.`
  else if (nova === atual) erros.nova = "A senha nova tem de ser diferente da atual."
  if (!erros.nova && repetir !== nova) erros.repetir = "As duas senhas novas não são iguais."
  return erros
}

const VAZIO: Campos = { atual: "", nova: "", repetir: "" }

const CAMPOS: { chave: keyof Campos; rotulo: string; autoComplete: string }[] = [
  { chave: "atual", rotulo: "Senha atual", autoComplete: "current-password" },
  { chave: "nova", rotulo: `Senha nova (pelo menos ${TAMANHO_MINIMO} caracteres)`, autoComplete: "new-password" },
  { chave: "repetir", rotulo: "Repita a senha nova", autoComplete: "new-password" },
]

export default function Senha() {
  const [campos, setCampos] = useState<Campos>(VAZIO)
  const [mostrarErros, setMostrarErros] = useState(false)
  const erros = mostrarErros ? errosDaSenha(campos) : {}

  const troca = useMutation({
    mutationFn: (c: Campos) =>
      apiJson<null>("/auth/web/senha", { method: "POST", json: { senha_atual: c.atual, senha_nova: c.nova } }),
    onSuccess: () => {
      setCampos(VAZIO)
      setMostrarErros(false)
      toast.success("Senha trocada. Use a senha nova no próximo login.")
    },
  })

  function enviar(e: FormEvent) {
    e.preventDefault()
    setMostrarErros(true)
    if (Object.keys(errosDaSenha(campos)).length > 0 || troca.isPending) return
    troca.mutate(campos)
  }

  return (
    <div className="space-y-6">
      <CabecalhoPagina sobretitulo="Configuração" titulo="Trocar senha" descricao="A senha vale para entrar no Frescor web." />
      <form onSubmit={enviar} noValidate className="painel max-w-md space-y-5 p-6">
        {troca.isError && (
          <Alert variant="erro" role="alert">
            <CircleAlert aria-hidden="true" />
            <AlertTitle>
              {troca.error instanceof ErroApi ? troca.error.message : "Não foi possível trocar a senha. Tente de novo."}
            </AlertTitle>
          </Alert>
        )}
        {CAMPOS.map(({ chave, rotulo, autoComplete }) => (
          <div key={chave} className="space-y-1.5">
            <Label htmlFor={`senha-${chave}`}>{rotulo}</Label>
            <Input
              id={`senha-${chave}`}
              type="password"
              autoComplete={autoComplete}
              value={campos[chave]}
              aria-invalid={erros[chave] ? true : undefined}
              aria-describedby={erros[chave] ? `senha-${chave}-erro` : undefined}
              onChange={(e) => {
                setCampos((c) => ({ ...c, [chave]: e.target.value }))
                troca.reset()
              }}
            />
            {erros[chave] && (
              <p id={`senha-${chave}-erro`} className="flex items-center gap-1.5 text-sm text-error">
                <CircleAlert className="size-4" aria-hidden="true" />
                {erros[chave]}
              </p>
            )}
          </div>
        ))}
        <Button type="submit" disabled={troca.isPending}>
          {troca.isPending ? "Trocando…" : "Trocar senha"}
        </Button>
      </form>
      <Toaster position="bottom-right" />
    </div>
  )
}
