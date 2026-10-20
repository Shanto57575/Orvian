import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from './App'

describe('App Starter Page', () => {
  it('renders Orvian header, title, and technology stack', () => {
    render(<App />)

    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(
      'Orvian Data Assistant',
    )
    expect(screen.getByText('API Health')).toBeInTheDocument()
    expect(screen.getByText('Technology Stack')).toBeInTheDocument()
    expect(screen.getByText('Synthetic Data Only')).toBeInTheDocument()
  })
})
