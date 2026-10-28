/*
 * Tela de login do gestor da central (passo W4, redesenhada em 28/10/2026),
 * seguindo a skill Frescor.
 *
 * Visual: à esquerda, o formulário sobre branco, com o logo no topo. À
 * direita (só no desktop), um painel liso em --secondary com uma frase
 * curta do produto e um recorte de uma ordem de produção, como o gestor vê
 * no sistema. O recorte é decorativo (aria-hidden) e usa dados de exemplo.
 * Sem degradê, brilho ou animação: o produto é o que aparece.
 *
 * Regras mantidas: uma única ação principal ("Entrar"), labels visíveis,
 * erro de campo com ícone abaixo do campo, erro do servidor num alerta com
 * o que houve e o que fazer (nada de "Erro 401"), aviso quando a sessão
 * terminou sozinha.
 */
import { useId, useRef, useState, type FormEvent } from "react"
import { CircleAlert, CircleCheck, TriangleAlert } from "lucide-react"
import { Navigate } from "react-router"
import { Logo } from "@/components/marca/Logo"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { ErroApi, MENSAGEM_SERVIDOR } from "@/lib/api/cliente"
import { useSessao } from "@/lib/sessao/contexto"

const EMAIL_VALIDO = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

interface ErroDaTela {
  titulo: string
  oQueFazer?: string
}

/** Traduz a falha do login em "o que houve + o que fazer". */
function erroDoLogin(erro: unknown): ErroDaTela {
  if (!(erro instanceof ErroApi)) return { titulo: MENSAGEM_SERVIDOR }
  if (erro.status === 401) return { titulo: "E-mail ou senha incorretos.", oQueFazer: "Confira os dados e tente de novo." }
  if (erro.status === 403 && /restrito a gestores/i.test(erro.message)) {
    return {
      titulo: erro.message,
      oQueFazer: "Se você é operador de loja, a contagem é feita no app do celular.",
    }
  }
  // 403 com outro motivo, sem conexão, servidor: a mensagem já diz o que fazer.
  return { titulo: erro.message }
}

/** Linhas do recorte de exemplo (produto, sugerido, final). */
const LINHAS_EXEMPLO = [
  { produto: "Pão Francês", sugerido: "142,0 kg", final: "144,6 kg" },
  { produto: "Croissant", sugerido: "139 un", final: "139 un" },
  { produto: "Baguete", sugerido: "98 un", final: "101 un" },
  { produto: "Pão de Queijo", sugerido: "31,2 kg", final: "31,2 kg" },
  { produto: "Bolo de Cenoura", sugerido: "43 un", final: "40 un" },
]

/** Recorte de uma ordem de produção, no mesmo desenho das telas do sistema. */
function RecorteOrdem() {
  return (
    <div
      aria-hidden="true"
      className="w-[720px] rounded-xl border border-white/10 bg-card text-foreground shadow-[0_24px_48px_-12px_rgb(0_0_0/0.35)] select-none"
    >
      <div className="flex items-center justify-between border-b border-line px-5 py-4">
        <div>
          <p className="font-heading text-base font-semibold text-heading">Produção de quinta, 29/10</p>
          <p className="text-sm text-muted-foreground">3 lojas · entrega às 6h</p>
        </div>
        <span className="inline-flex items-center gap-1 rounded-full bg-success-bg px-2.5 py-0.5 text-sm font-semibold text-success">
          <CircleCheck className="size-4" />
          Aprovada
        </span>
      </div>
      <table className="w-full text-[15px]">
        <thead className="bg-surface/80 text-left text-xs font-semibold text-muted-foreground uppercase">
          <tr>
            <th className="h-9 px-5 font-semibold">Produto</th>
            <th className="h-9 px-5 text-right font-semibold">Sugerido</th>
            <th className="h-9 px-5 text-right font-semibold">Final</th>
          </tr>
        </thead>
        <tbody>
          {LINHAS_EXEMPLO.map((l) => (
            <tr key={l.produto} className="border-t border-line/70">
              <td className="h-11 px-5 font-semibold">{l.produto}</td>
              <td className="h-11 px-5 text-right text-muted-foreground numero">{l.sugerido}</td>
              <td className="h-11 px-5 text-right font-semibold numero">{l.final}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function Entrar() {
  const { autenticado, motivoSaida, entrar } = useSessao()
  const [email, setEmail] = useState("")
  const [senha, setSenha] = useState("")
  const [erroEmail, setErroEmail] = useState<string | null>(null)
  const [erroSenha, setErroSenha] = useState<string | null>(null)
  const [erroServidor, setErroServidor] = useState<ErroDaTela | null>(null)
  const [enviando, setEnviando] = useState(false)
  const campoEmail = useRef<HTMLInputElement>(null)
  const campoSenha = useRef<HTMLInputElement>(null)
  const id = useId()

  if (autenticado) return <Navigate to="/" replace />

  async function aoEnviar(evento: FormEvent<HTMLFormElement>) {
    evento.preventDefault()
    setErroServidor(null)

    const emailLimpo = email.trim()
    const novoErroEmail = !emailLimpo
      ? "Informe o e-mail."
      : !EMAIL_VALIDO.test(emailLimpo)
        ? "Confira o e-mail: ele precisa ter @ e um domínio, como nome@empresa.com.br."
        : null
    const novoErroSenha = senha ? null : "Informe a senha."
    setErroEmail(novoErroEmail)
    setErroSenha(novoErroSenha)
    if (novoErroEmail) return campoEmail.current?.focus()
    if (novoErroSenha) return campoSenha.current?.focus()

    setEnviando(true)
    try {
      await entrar(emailLimpo, senha)
    } catch (erro) {
      setErroServidor(erroDoLogin(erro))
      setEnviando(false)
    }
  }

  return (
    <main className="min-h-screen bg-card lg:grid lg:grid-cols-2">
      {/* Lado do formulário. */}
      <section className="flex min-h-screen flex-col px-6 py-8 sm:px-12 lg:px-16">
        <Logo tamanho={28} className="[&>span:last-child]:text-[22px]" />

        <div className="flex flex-1 items-center py-12">
          <div className="w-full max-w-[380px]">
            <h1 className="text-[28px] leading-tight">Entrar</h1>
            <p className="mt-2 text-muted-foreground">Use o e-mail e a senha de gestor da central.</p>

            <div aria-live="polite" className="mt-6 empty:hidden">
              {motivoSaida && !erroServidor && (
                <Alert variant="aviso">
                  <TriangleAlert aria-hidden="true" />
                  <AlertTitle>{motivoSaida}</AlertTitle>
                </Alert>
              )}
              {erroServidor && (
                <Alert variant="erro">
                  <CircleAlert aria-hidden="true" />
                  <AlertTitle>{erroServidor.titulo}</AlertTitle>
                  {erroServidor.oQueFazer && <AlertDescription>{erroServidor.oQueFazer}</AlertDescription>}
                </Alert>
              )}
            </div>

            <form className="mt-8 flex flex-col gap-5" onSubmit={aoEnviar} noValidate>
              <div className="flex flex-col gap-2">
                <Label htmlFor={`${id}-email`}>E-mail</Label>
                <Input
                  ref={campoEmail}
                  id={`${id}-email`}
                  type="email"
                  autoComplete="username"
                  inputMode="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  aria-invalid={erroEmail ? true : undefined}
                  aria-describedby={erroEmail ? `${id}-email-erro` : undefined}
                />
                {erroEmail && (
                  <p id={`${id}-email-erro`} className="flex items-start gap-2 text-sm text-error">
                    <CircleAlert className="size-5 shrink-0" aria-hidden="true" />
                    {erroEmail}
                  </p>
                )}
              </div>

              <div className="flex flex-col gap-2">
                <Label htmlFor={`${id}-senha`}>Senha</Label>
                <Input
                  ref={campoSenha}
                  id={`${id}-senha`}
                  type="password"
                  autoComplete="current-password"
                  value={senha}
                  onChange={(e) => setSenha(e.target.value)}
                  aria-invalid={erroSenha ? true : undefined}
                  aria-describedby={erroSenha ? `${id}-senha-erro` : undefined}
                />
                {erroSenha && (
                  <p id={`${id}-senha-erro`} className="flex items-start gap-2 text-sm text-error">
                    <CircleAlert className="size-5 shrink-0" aria-hidden="true" />
                    {erroSenha}
                  </p>
                )}
              </div>

              <Button type="submit" className="mt-1 w-full" carregando={enviando} textoCarregando="Entrando…">
                Entrar
              </Button>
            </form>
          </div>
        </div>

        <p className="text-sm text-muted-foreground">Operador de loja? A contagem é feita no app do celular.</p>
      </section>

      {/* Lado do produto (só no desktop): frase curta e o recorte da ordem, sangrando pela direita. */}
      <section aria-hidden="true" className="hidden overflow-hidden bg-heading lg:flex lg:flex-col lg:justify-center lg:py-16 lg:pl-16">
        <div className="max-w-md pr-16">
          <p className="text-sm font-semibold text-highlight">Central de produção</p>
          <p className="mt-3 font-heading text-[32px] leading-[1.2] font-semibold tracking-[-0.02em] text-white">
            Da previsão de vendas ao romaneio, num só lugar.
          </p>
          <p className="mt-4 text-ink-muted">
            Cada loja recebe o que deve vender amanhã, com a conta de cada número à vista.
          </p>
        </div>
        <div className="mt-12">
          <RecorteOrdem />
        </div>
      </section>
    </main>
  )
}
