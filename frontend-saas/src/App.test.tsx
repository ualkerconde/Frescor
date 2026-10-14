import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from './App'

describe('App (esqueleto do W2)', () => {
  it('renderiza o nome do produto', () => {
    render(<App />)
    expect(screen.getByRole('heading', { level: 1, name: 'Frescor' })).toBeInTheDocument()
  })
})
