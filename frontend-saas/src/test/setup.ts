// Matchers do Testing Library (toBeInTheDocument, toBeDisabled...) e
// limpeza do DOM entre um teste e outro.
import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(() => {
  cleanup()
})
