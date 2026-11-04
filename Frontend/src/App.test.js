import { render, screen } from '@testing-library/react';
import App from './App';

beforeEach(() => {
  window.localStorage.removeItem('kr-token');
});

test('renders the farm login page', () => {
  render(<App />);
  expect(screen.getByRole('heading', { name: /welcome back/i })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /^log in$/i })).toBeInTheDocument();
});
