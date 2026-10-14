// Matchers do Testing Library (toBeInTheDocument, toBeDisabled...) e
// limpeza do DOM entre um teste e outro.
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(() => {
  cleanup()
})

// APIs de navegador que o jsdom não tem e que o Radix (Select, Popover) e o
// cmdk (Command) usam. Substitutos mínimos, só para os testes rodarem.
class ResizeObserverDeTeste {
  observe() {}
  unobserve() {}
  disconnect() {}
}
// Só onde há DOM (o teste do tema roda no ambiente Node, sem Element).
if (typeof Element !== 'undefined') {
  globalThis.ResizeObserver ??= ResizeObserverDeTeste as unknown as typeof ResizeObserver
  Element.prototype.scrollIntoView ??= function () {}
  Element.prototype.hasPointerCapture ??= () => false
  Element.prototype.releasePointerCapture ??= () => {}
}
