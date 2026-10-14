/*
 * Consulta de vendas e perdas: chega no W7. Por enquanto, estado vazio útil
 * (skill: dizer o que vai aparecer ali e oferecer o próximo passo).
 */
import { Upload } from "lucide-react"
import { Link } from "react-router"
import { buttonVariants } from "@/components/ui/button"

export function Consultar() {
  return (
    <section>
      <h1 className="text-[28px]">Consultar vendas e perdas</h1>
      <div className="mt-6 rounded-lg bg-surface p-6">
        <p className="text-foreground">
          Aqui você vai ver as vendas e perdas importadas, por período, loja e produto.
        </p>
        <p className="mt-1 text-muted-foreground">Esta tela está em construção. Enquanto isso, você já pode importar os arquivos.</p>
        <Link to="/importar" className={buttonVariants({ variant: "secondary", className: "mt-4" })}>
          <Upload aria-hidden="true" />
          Ir para a importação
        </Link>
      </div>
    </section>
  )
}
