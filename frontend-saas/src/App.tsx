/*
 * Rotas do frontend do SaaS.
 * /entrar: login do gestor.
 * Área autenticada (LayoutAutenticado): /importar, /consultar, /previsao, /producao, /distribuicao
 * e /cadastros (produtos, setores e central, com as sub-rotas dentro da própria tela).
 * / e qualquer outra rota -> /importar (ou login, sem sessão).
 *
 * Telas novas (a partir da Fase 3) entram com o código dividido por tela:
 * React.lazy + import(), carregadas só quando abertas (regra do W8).
 */
import { lazy, Suspense } from "react"
import { Navigate, Route, Routes } from "react-router"
import { LayoutAutenticado } from "@/components/layout/LayoutAutenticado"
import { RotaProtegida } from "@/lib/sessao/RotaProtegida"
import { Consultar } from "@/paginas/Consultar"
import { Entrar } from "@/paginas/Entrar"
import { Importar } from "@/paginas/Importar"

const Previsao = lazy(() => import("@/paginas/Previsao").then((m) => ({ default: m.Previsao })))
const Producao = lazy(() => import("@/paginas/Producao").then((m) => ({ default: m.Producao })))
const Distribuicao = lazy(() => import("@/paginas/Distribuicao").then((m) => ({ default: m.Distribuicao })))
const Cadastros = lazy(() => import("@/paginas/Cadastros").then((m) => ({ default: m.Cadastros })))

function Carregando() {
  return <p className="text-muted-foreground">Carregando…</p>
}

function App() {
  return (
    <Routes>
      <Route path="/entrar" element={<Entrar />} />
      <Route
        element={
          <RotaProtegida>
            <LayoutAutenticado />
          </RotaProtegida>
        }
      >
        <Route path="/importar" element={<Importar />} />
        <Route path="/consultar" element={<Consultar />} />
        <Route
          path="/previsao"
          element={
            <Suspense fallback={<Carregando />}>
              <Previsao />
            </Suspense>
          }
        />
        <Route
          path="/producao"
          element={
            <Suspense fallback={<Carregando />}>
              <Producao />
            </Suspense>
          }
        />
        <Route
          path="/distribuicao"
          element={
            <Suspense fallback={<Carregando />}>
              <Distribuicao />
            </Suspense>
          }
        />
        <Route
          path="/cadastros/*"
          element={
            <Suspense fallback={<Carregando />}>
              <Cadastros />
            </Suspense>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/importar" replace />} />
    </Routes>
  )
}

export default App
