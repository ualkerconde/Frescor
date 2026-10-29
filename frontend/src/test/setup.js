// Matchers do Testing Library (toBeInTheDocument, toBeDisabled...) e
// limpeza do DOM e dos mocks entre um teste e outro.
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  localStorage.clear()
})
