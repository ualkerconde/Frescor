/*
 * Rotas do frontend do SaaS.
 * /entrar: login do gestor.
 * Área autenticada (LayoutAutenticado): /importar, /consultar, /previsao e /producao.
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
      </Route>
      <Route path="*" element={<Navigate to="/importar" replace />} />
    </Routes>
  )
}

export default App
