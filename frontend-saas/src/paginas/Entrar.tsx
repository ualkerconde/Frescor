/*
 * Tela de login do gestor da central (passo W4), seguindo a skill Frescor:
 * uma única ação principal ("Entrar"), labels visíveis, erro de campo com
 * ícone abaixo do campo, erro do servidor num alerta com o que houve e o
 * que fazer (nada de "Erro 401"), aviso quando a sessão terminou sozinha.
 */
import { useId, useRef, useState, type FormEvent } from "react"
import { CircleAlert, LogIn, TriangleAlert } from "lucide-react"
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
    <main className="flex min-h-screen items-center justify-center bg-background px-4 py-12">
      <div className="w-full max-w-sm rounded-lg border border-line bg-card p-6 shadow-elevado sm:p-8">
        <div className="flex flex-col items-center text-center">
          <Logo />
          <p className="mt-2 text-sm text-muted-foreground">Central de produção</p>
          <h1 className="mt-6 text-[22px]">Entrar</h1>
          <p className="mt-1 text-sm text-muted-foreground">Use o e-mail e a senha de gestor da central.</p>
        </div>

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

        <form className="mt-6 flex flex-col gap-5" onSubmit={aoEnviar} noValidate>
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
            <LogIn aria-hidden="true" />
            Entrar
          </Button>
        </form>
      </div>
    </main>
  )
}
