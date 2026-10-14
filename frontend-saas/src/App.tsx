/*
 * Rotas do frontend do SaaS.
 * /entrar: login do gestor.
 * Área autenticada (LayoutAutenticado): /importar e /consultar.
 * / e qualquer outra rota -> /importar (ou login, sem sessão).
 */
import { Navigate, Route, Routes } from "react-router"
import { LayoutAutenticado } from "@/components/layout/LayoutAutenticado"
import { RotaProtegida } from "@/lib/sessao/RotaProtegida"
import { Consultar } from "@/paginas/Consultar"
import { Entrar } from "@/paginas/Entrar"
import { Importar } from "@/paginas/Importar"

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
      </Route>
      <Route path="*" element={<Navigate to="/importar" replace />} />
    </Routes>
  )
}

export default App
