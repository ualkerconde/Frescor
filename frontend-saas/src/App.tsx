/*
 * Rotas do frontend do SaaS.
 * /entrar: login do gestor. /: área autenticada (provisória até o W5).
 */
import { Navigate, Route, Routes } from "react-router"
import { Entrar } from "@/paginas/Entrar"
import { PainelProvisorio } from "@/paginas/PainelProvisorio"
import { RotaProtegida } from "@/lib/sessao/RotaProtegida"

function App() {
  return (
    <Routes>
      <Route path="/entrar" element={<Entrar />} />
      <Route
        path="/"
        element={
          <RotaProtegida>
            <PainelProvisorio />
          </RotaProtegida>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default App
