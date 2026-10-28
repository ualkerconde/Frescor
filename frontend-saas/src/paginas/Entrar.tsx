/*
 * Tela de login do gestor da central (passo W4, redesenhada em 28/10/2026),
 * seguindo a skill Frescor.
 *
 * Visual: fundo escuro da marca (--secondary -> --ink) com uma "aurora"
 * verde e dourada que se move devagar (para com prefers-reduced-motion).
 * No desktop, à esquerda, a promessa do produto e uma ilustração feita de
 * cartões de vidro (previsão, ordem aprovada, quebra); à direita, o
 * formulário num painel claro. No celular, só o logo e o formulário.
 * A ilustração é decorativa (aria-hidden): os números são de exemplo.
 *
 * Regras mantidas: uma única ação principal ("Entrar"), labels visíveis,
 * erro de campo com ícone abaixo do campo, erro do servidor num alerta com
 * o que houve e o que fazer (nada de "Erro 401"), aviso quando a sessão
 * terminou sozinha.
 */
import { useId, useRef, useState, type FormEvent } from "react"
import { CircleAlert, CircleCheck, LockKeyhole, LogIn, Mail, TrendingDown, TriangleAlert } from "lucide-react"
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

/** Barras da ilustração: previsto (altura) e vendido (marcador), em % da altura. */
const BARRAS = [
  { dia: "S", previsto: 62, vendido: 58 },
  { dia: "T", previsto: 54, vendido: 55 },
  { dia: "Q", previsto: 70, vendido: 66 },
  { dia: "Q", previsto: 66, vendido: 69 },
  { dia: "S", previsto: 84, vendido: 80 },
  { dia: "S", previsto: 100, vendido: 96 },
  { dia: "D", previsto: 76, vendido: 73 },
]

/** Ilustração decorativa do painel escuro: cartões de vidro com dados de exemplo. */
function Ilustracao() {
  return (
    <div aria-hidden="true" className="relative mx-auto h-[340px] w-full max-w-[520px] select-none">
      {/* Cartão principal: previsão da semana. */}
      <div className="absolute inset-x-6 top-6 rounded-2xl border border-white/10 bg-white/[0.06] p-5 shadow-[0_24px_60px_-20px_rgb(0_0_0/0.6)] backdrop-blur-md">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold tracking-[0.12em] text-ink-muted uppercase">Previsão da semana</p>
            <p className="mt-1 font-heading text-[28px] leading-none font-bold tracking-[-0.03em] text-white numero">
              8.420 <span className="text-base font-semibold text-ink-muted">un</span>
            </p>
          </div>
          <span className="inline-flex items-center gap-1.5 rounded-full bg-mint/15 px-2.5 py-1 text-xs font-semibold text-mint">
            <span className="size-1.5 rounded-full bg-mint" />
            erro médio 4,1%
          </span>
        </div>
        <div className="mt-5 flex h-32 items-end gap-3">
          {BARRAS.map((b, i) => (
            <div key={i} className="flex h-full flex-1 flex-col items-center justify-end gap-2">
              <div className="relative w-full flex-1">
                <div
                  className="absolute inset-x-0 bottom-0 rounded-t-md bg-linear-to-t from-primary to-mint/90"
                  style={{ height: `${b.previsto}%` }}
                />
                <div
                  className="absolute inset-x-[-3px] h-[3px] rounded-full bg-highlight"
                  style={{ bottom: `calc(${b.vendido}% - 1.5px)` }}
                />
              </div>
              <span className="text-xs font-semibold text-ink-muted">{b.dia}</span>
            </div>
          ))}
        </div>
        <div className="mt-3 flex gap-4 text-xs text-ink-muted">
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2 rounded-sm bg-mint" /> Previsto
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-[3px] w-3 rounded-full bg-highlight" /> Vendido
          </span>
        </div>
      </div>

      {/* Cartão flutuante: ordem aprovada. */}
      <div className="absolute -right-2 -bottom-2 w-56 animate-flutuar rounded-2xl border border-white/10 bg-ink/80 p-4 shadow-[0_20px_50px_-18px_rgb(0_0_0/0.7)] backdrop-blur-md">
        <p className="text-xs font-semibold tracking-[0.12em] text-ink-muted uppercase">Ordem de amanhã</p>
        <p className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-mint/15 px-2.5 py-1 text-sm font-semibold text-mint">
          <CircleCheck className="size-4" />
          Aprovada
        </p>
        <p className="mt-2 text-sm text-white numero">1.240 un · 18 produtos</p>
      </div>

      {/* Cartão flutuante: quebra. */}
      <div className="absolute -bottom-6 left-0 w-48 animate-flutuar rounded-2xl border border-white/10 bg-ink/80 p-4 shadow-[0_20px_50px_-18px_rgb(0_0_0/0.7)] backdrop-blur-md [animation-delay:-3.5s]">
        <p className="text-xs font-semibold tracking-[0.12em] text-ink-muted uppercase">Quebra</p>
        <p className="mt-1 font-heading text-[26px] leading-none font-bold tracking-[-0.03em] text-white numero">2,8%</p>
        <p className="mt-1.5 flex items-center gap-1 text-sm font-semibold text-mint numero">
          <TrendingDown className="size-4" />
          1,4 p.p. no mês
        </p>
      </div>
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
    <main className="relative isolate min-h-screen overflow-hidden bg-linear-to-br from-heading via-ink to-ink lg:grid lg:grid-cols-[minmax(0,1.15fr)_minmax(480px,1fr)]">
      {/* Aurora: dois brilhos desfocados que se movem devagar, e a trama de pontos. */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute -top-40 -left-32 size-[560px] animate-aurora rounded-full bg-primary opacity-55 blur-[110px]" />
        <div className="absolute top-1/3 left-1/3 size-[420px] animate-aurora rounded-full bg-highlight opacity-[0.14] blur-[120px] [animation-delay:-9s]" />
        <div className="absolute -bottom-40 left-10 size-[380px] animate-aurora rounded-full bg-mint opacity-20 blur-[110px] [animation-delay:-5s]" />
        <div className="absolute inset-0 trama-pontos [mask-image:radial-gradient(ellipse_at_30%_40%,black,transparent_75%)]" />
      </div>

      {/* Lado da marca (o logo aparece também no celular, acima do formulário). */}
      <section className="flex flex-col px-6 pt-8 pb-6 sm:px-10 lg:min-h-screen lg:px-14 lg:py-12 xl:px-20">
        <Logo tamanho={38} sobreEscuro />

        <div className="hidden flex-1 flex-col justify-center gap-12 py-10 lg:flex">
          <div className="max-w-xl">
            <p className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.06] px-3 py-1 text-sm font-semibold text-ink-muted backdrop-blur">
              <span className="size-2 animate-pulsar rounded-full bg-mint" aria-hidden="true" />
              Central de produção
            </p>
            <p className="mt-6 font-heading text-[44px] leading-[1.08] font-bold tracking-[-0.035em] text-white xl:text-[54px]">
              Produza o que a loja{" "}
              <span className="bg-linear-to-r from-mint to-highlight bg-clip-text text-transparent">vai vender.</span>
            </p>
            <p className="mt-5 max-w-md text-lg text-ink-muted">
              Previsão de vendas, ordem de produção e romaneio no mesmo lugar, para cada loja receber o que precisa
              com menos quebra.
            </p>
          </div>
          <Ilustracao />
        </div>

        <p className="hidden text-sm text-ink-muted lg:block">Padaria · Açougue · Hortifruti</p>
      </section>

      {/* Lado do formulário. */}
      <section className="flex items-start justify-center px-4 pb-12 sm:px-6 lg:items-center lg:bg-background lg:px-10 lg:py-12 lg:shadow-[-24px_0_80px_-24px_rgb(0_0_0/0.5)]">
        <div className="w-full max-w-[400px] animate-surgir rounded-2xl bg-card p-6 shadow-[0_24px_64px_-16px_rgb(0_0_0/0.5)] sm:p-8 lg:rounded-none lg:bg-transparent lg:p-0 lg:shadow-none">
          <p className="text-sm font-semibold tracking-[0.12em] text-primary uppercase">Painel do gestor</p>
          <h1 className="mt-2 text-[36px] leading-tight font-bold tracking-[-0.03em]">Entrar</h1>
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
              <div className="relative">
                <Mail
                  className="pointer-events-none absolute top-1/2 left-3.5 size-5 -translate-y-1/2 text-muted-foreground"
                  aria-hidden="true"
                />
                <Input
                  ref={campoEmail}
                  id={`${id}-email`}
                  type="email"
                  autoComplete="username"
                  inputMode="email"
                  placeholder="nome@empresa.com.br"
                  className="h-12 pl-11"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  aria-invalid={erroEmail ? true : undefined}
                  aria-describedby={erroEmail ? `${id}-email-erro` : undefined}
                />
              </div>
              {erroEmail && (
                <p id={`${id}-email-erro`} className="flex items-start gap-2 text-sm text-error">
                  <CircleAlert className="size-5 shrink-0" aria-hidden="true" />
                  {erroEmail}
                </p>
              )}
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor={`${id}-senha`}>Senha</Label>
              <div className="relative">
                <LockKeyhole
                  className="pointer-events-none absolute top-1/2 left-3.5 size-5 -translate-y-1/2 text-muted-foreground"
                  aria-hidden="true"
                />
                <Input
                  ref={campoSenha}
                  id={`${id}-senha`}
                  type="password"
                  autoComplete="current-password"
                  className="h-12 pl-11"
                  value={senha}
                  onChange={(e) => setSenha(e.target.value)}
                  aria-invalid={erroSenha ? true : undefined}
                  aria-describedby={erroSenha ? `${id}-senha-erro` : undefined}
                />
              </div>
              {erroSenha && (
                <p id={`${id}-senha-erro`} className="flex items-start gap-2 text-sm text-error">
                  <CircleAlert className="size-5 shrink-0" aria-hidden="true" />
                  {erroSenha}
                </p>
              )}
            </div>

            <Button type="submit" size="lg" className="mt-2 w-full" carregando={enviando} textoCarregando="Entrando…">
              <LogIn aria-hidden="true" />
              Entrar
            </Button>
          </form>

          <p className="mt-8 border-t border-line pt-5 text-sm text-muted-foreground">
            Operador de loja? A contagem é feita no app do celular.
          </p>
        </div>
      </section>
    </main>
  )
}
