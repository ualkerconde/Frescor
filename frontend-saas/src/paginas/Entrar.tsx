/*
 * Tela de login do gestor da central (passo W4, redesenhada em 28/10/2026 e
 * em 13/11/2026 no visual "Comando" azul-noite e âmbar, D117), seguindo a
 * skill Frescor.
 *
 * Visual: à esquerda (520px), o selo, a saudação grande pela hora do dia
 * ("Bom dia. A fornada de hoje já está calculada.") e o formulário. À
 * direita (só no desktop), a vitrine: o número grande de acerto da
 * previsão, a linha previsto × vendido e três cartões. A vitrine é
 * decorativa (aria-hidden) e diz na própria tela que é um EXEMPLO: antes
 * do login não há dado real para mostrar, e número inventado não pode
 * parecer o do cliente.
 *
 * Regras mantidas: uma única ação principal ("Entrar"), labels visíveis,
 * erro de campo com ícone abaixo do campo, erro do servidor num alerta com
 * o que houve e o que fazer (nada de "Erro 401"), aviso quando a sessão
 * terminou sozinha.
 */
import { useId, useRef, useState, type FormEvent } from "react"
import { CircleAlert, TriangleAlert } from "lucide-react"
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

/** Saudação pela hora local: a mesma regra da tela inicial. */
function saudacao(agora = new Date()): string {
  const h = agora.getHours()
  return h < 12 ? "Bom dia." : h < 18 ? "Boa tarde." : "Boa noite."
}

/* Linha de exemplo (14 dias): vendido e previsto, em coordenadas do SVG 920×260. */
const VENDIDO_EXEMPLO = "0,190 70,176 140,160 210,96 280,80 350,150 420,178 490,166 560,156 630,92 700,74 770,146 840,170 920,150"
const PREVISTO_EXEMPLO = "0,184 70,172 140,162 210,102 280,86 350,146 420,172 490,166 560,152 630,98 700,82 770,142 840,166 920,146"

/** Vitrine do lado direito (decorativa, com dados de exemplo assumidos como tal). */
function Vitrine() {
  return (
    <section aria-hidden="true" className="relative hidden overflow-hidden select-none lg:block">
      <div className="px-14 pt-14">
        <p className="text-xs font-semibold tracking-[0.14em] text-muted-foreground uppercase">
          Exemplo de uma central · última semana
        </p>
        <p className="mt-4 font-mono text-[112px] leading-none font-semibold tracking-[-0.05em] text-heading">
          91,8<span className="text-primary">%</span>
        </p>
        <p className="mt-3 max-w-[520px] text-xl text-muted-foreground">
          de acerto na previsão de venda. Cada loja recebe o que vai vender, não o que sobrou da intuição.
        </p>
      </div>

      <svg className="absolute inset-x-0 top-[330px] h-[300px] w-full" viewBox="0 0 920 260" preserveAspectRatio="none">
        <g stroke="var(--fr-line)" strokeWidth="1">
          <line x1="0" y1="60" x2="920" y2="60" />
          <line x1="0" y1="130" x2="920" y2="130" />
          <line x1="0" y1="200" x2="920" y2="200" />
        </g>
        <polyline
          fill="none"
          stroke="var(--fr-blue)"
          strokeWidth="2"
          strokeDasharray="6 5"
          vectorEffect="non-scaling-stroke"
          points={PREVISTO_EXEMPLO}
        />
        <polyline
          fill="none"
          stroke="var(--fr-primary)"
          strokeWidth="3"
          vectorEffect="non-scaling-stroke"
          points={VENDIDO_EXEMPLO}
        />
      </svg>

      <div className="absolute right-[-40px] bottom-14 left-14 grid grid-cols-[1.3fr_1fr_1fr] gap-4">
        <div className="rounded-2xl border border-line bg-card p-5">
          <p className="text-sm text-muted-foreground">Ordem de sábado</p>
          <p className="mt-1.5 font-mono text-3xl font-semibold tracking-[-0.02em] text-heading">4.812 un</p>
          <p className="mt-1 text-sm text-primary">● pronta para aprovar</p>
        </div>
        <div className="rounded-2xl border border-line bg-card p-5">
          <p className="text-sm text-muted-foreground">Perda</p>
          <p className="mt-1.5 font-mono text-3xl font-semibold tracking-[-0.02em] text-heading">4,1%</p>
          <p className="mt-1 text-sm text-primary">▼ 0,9 pt no mês</p>
        </div>
        <div className="rounded-2xl border border-line bg-card p-5">
          <p className="text-sm text-muted-foreground">Lojas que contaram</p>
          <p className="mt-1.5 font-mono text-3xl font-semibold tracking-[-0.02em] text-heading">12/12</p>
          <p className="mt-1 text-sm text-muted-foreground">até 21h de ontem</p>
        </div>
      </div>
    </section>
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
    <main className="min-h-screen bg-background lg:grid lg:grid-cols-[520px_minmax(0,1fr)]">
      {/* Lado do formulário. */}
      <section className="flex min-h-screen flex-col px-6 py-8 sm:px-12 lg:border-r lg:border-line lg:px-16 lg:py-14">
        <Logo tamanho={40} className="[&>span:last-child]:text-[22px]" />

        <div className="flex flex-1 items-center py-12">
          <div className="w-full max-w-[392px]">
            <p className="font-heading text-[40px] leading-[1.05] font-semibold tracking-[-0.035em] text-heading sm:text-[44px]">
              {saudacao()}
              <br />A fornada de hoje
              <br />
              já está calculada.
            </p>
            <h1 className="mt-8 text-xs font-semibold tracking-[0.14em] text-muted-foreground uppercase">Entrar</h1>
            <p className="mt-1 text-muted-foreground">
              Use o e-mail e a senha de gestor da central para ver a ordem de produção e o que cada loja precisa.
            </p>

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

              <Button type="submit" size="lg" className="mt-1 w-full" carregando={enviando} textoCarregando="Entrando…">
                Entrar
              </Button>
            </form>
          </div>
        </div>

        <p className="text-sm text-muted-foreground">Operador de loja? A contagem é feita no app do celular.</p>
      </section>

      <Vitrine />
    </main>
  )
}
