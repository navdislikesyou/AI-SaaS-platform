/**
 * Tests for the dataset format guidance on the Performance page.
 *
 * The Performance service is mocked, so these tests assert only what the page
 * claims about dataset formats. That is the point: the copy must stay inside
 * what the backend loader and the per-analyzer column checks actually do, so a
 * claim like "every operation needs these columns" would be a regression even
 * though the box would still render.
 *
 * Nothing here submits a job or reads pandas. The Dataset Source tab is
 * reached by clicking the tab, so no request is made.
 */

import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import PerformanceAIPage from './PerformanceAIPage';
import { AuthProvider } from '../context/AuthContext';
import { performanceService } from '../services/performanceService';

vi.mock('../services/performanceService', async (importOriginal) => {
  const actual = await importOriginal();

  return {
    ...actual,
    performanceService: {
      artifactUrl: vi.fn(() => 'https://example.test/chart.png'),
      createJob: vi.fn(),
      getJob: vi.fn(),
    },
  };
});

function renderPage() {
  return render(
    <MemoryRouter>
      <AuthProvider>
        <PerformanceAIPage />
      </AuthProvider>
    </MemoryRouter>
  );
}

/**
 * Open the Dataset Source tab and return its format guidance box.
 *
 * @returns {Promise<HTMLElement>}
 */
async function findFormatBox() {
  renderPage();

  await userEvent.click(screen.getByRole('button', { name: /Dataset Source/i }));

  return (await screen.findByText('Dataset format')).closest('.saas-info-box');
}

beforeEach(() => {
  vi.mocked(performanceService.createJob).mockReset();
  vi.mocked(performanceService.getJob).mockReset();
});

describe('PerformanceAIPage dataset format guidance', () => {
  it('explains that the dataset is read from the server, not the browser', async () => {
    const box = await findFormatBox();

    expect(box).toHaveTextContent(/no upload control/i);
    expect(box).toHaveTextContent(/already exist on the machine running the backend/i);
    expect(box).toHaveTextContent(/resolves from the\s*backend\//i);
  });

  it('documents csv and xlsx and not xls', async () => {
    const box = await findFormatBox();

    expect(box).toHaveTextContent(/\.csv/);
    expect(box).toHaveTextContent(/\.xlsx/);
    // ".xlsx" contains ".xls" as a substring, so the negative match has to
    // exclude a following letter rather than the bare prefix.
    expect(box.textContent).not.toMatch(/\.xls(?![a-z])/);
  });

  it('drops xls from the playground format hint too', async () => {
    renderPage();

    const hint = await screen.findByText(/Relative paths resolve from/i);

    expect(hint).toHaveTextContent(/\.csv/);
    expect(hint).toHaveTextContent(/\.xlsx/);
    expect(hint.textContent).not.toMatch(/\.xls(?![a-z])/);
  });

  it('warns that only the first worksheet is read', async () => {
    const box = await findFormatBox();

    expect(box).toHaveTextContent(/first worksheet/i);
  });

  it('does not claim every operation requires the same columns', async () => {
    const box = await findFormatBox();

    expect(box).toHaveTextContent(/Columns are not uniform across operations/i);
    expect(box).toHaveTextContent(/compare_periods/);
    expect(box).toHaveTextContent(/fails the job without it/i);
    expect(box).toHaveTextContent(/does not\s+reject a missing column/i);
    expect(box).toHaveTextContent(/left out rather than guessed/i);
  });

  it('labels the extra columns as optional rather than required', async () => {
    const box = await findFormatBox();

    expect(box.querySelectorAll('.saas-info-opt').length).toBeGreaterThan(0);
    expect(box).toHaveTextContent(/These add analysis rather than unlocking it/i);
  });

  it('explains header normalization so a spaced header still matches', async () => {
    const box = await findFormatBox();

    expect(box).toHaveTextContent(/sales_channel/);
  });

  it('keeps the example header row collapsed until asked for', async () => {
    const user = userEvent.setup();
    const box = await findFormatBox();

    const toggle = screen.getByRole('button', { name: /Example header row/i });

    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText(/Financials\.csv — header only/)).not.toBeInTheDocument();

    await user.click(toggle);

    expect(box).toHaveTextContent(/employee_id/);
    expect(screen.getByText(/Financials\.csv — header only/)).toBeInTheDocument();
  });

  it('places the guidance inside the Dataset Source section', async () => {
    renderPage();

    await userEvent.click(screen.getByRole('button', { name: /Dataset Source/i }));

    const title = await screen.findByText('Dataset format');
    const section = title.closest('.saas-card');

    // The box has to sit alongside the path control it explains, not on the
    // Playground tab where the same path field also appears.
    expect(
      within(section).getByPlaceholderText(/Financials_standardized\.csv/)
    ).toBeInTheDocument();
  });
});