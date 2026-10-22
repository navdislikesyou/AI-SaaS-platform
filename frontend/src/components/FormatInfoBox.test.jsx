/**
 * Tests for the shared format guidance box.
 *
 * The box is presentation only, so what matters is that a rule is visible
 * without being expanded, that an example stays collapsed until asked for, and
 * that the toggle reports its state to assistive technology.
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import FormatInfoBox, { FormatInfoSample } from './FormatInfoBox';

function renderBox(props = {}) {
  return render(
    <FormatInfoBox
      title="Preparing your document"
      accent="#E8FF72"
      accentRgb="232, 255, 114"
      {...props}
    >
      <p>
        <span className="saas-info-req">Required</span>
        A .pdf, .docx, or .txt file.
      </p>
    </FormatInfoBox>
  );
}

describe('FormatInfoBox', () => {
  it('shows the title and body rules without expanding anything', () => {
    renderBox();

    expect(screen.getByText('Preparing your document')).toBeInTheDocument();
    expect(screen.getByText('Required')).toBeInTheDocument();
    expect(screen.getByText(/A \.pdf, \.docx, or \.txt file\./)).toBeInTheDocument();
  });

  it('renders no toggle when no example is supplied', () => {
    renderBox();

    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('keeps an example collapsed until the toggle is used', async () => {
    const user = userEvent.setup();

    renderBox({
      examples: [{ label: 'CSV example', content: <p>name,email</p> }],
    });

    const toggle = screen.getByRole('button', { name: /CSV example/i });

    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByText('name,email')).not.toBeInTheDocument();

    await user.click(toggle);

    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    expect(screen.getByText('name,email')).toBeInTheDocument();
  });

  it('collapses the example again on a second click', async () => {
    const user = userEvent.setup();

    renderBox({
      examples: [{ label: 'CSV example', content: <p>name,email</p> }],
    });

    const toggle = screen.getByRole('button', { name: /CSV example/i });

    await user.click(toggle);
    await user.click(screen.getByRole('button', { name: /Hide CSV example/i }));

    expect(screen.queryByText('name,email')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /CSV example/i })).toHaveAttribute(
      'aria-expanded',
      'false'
    );
  });

  it('gives each example its own independently collapsible region', async () => {
    const user = userEvent.setup();

    renderBox({
      examples: [
        { label: 'CSV example', content: <p>csv-body-marker</p> },
        { label: 'JSON example', content: <p>json-body-marker</p> },
      ],
    });

    await user.click(screen.getByRole('button', { name: /CSV example/i }));

    expect(screen.getByText('csv-body-marker')).toBeInTheDocument();
    expect(screen.queryByText('json-body-marker')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /JSON example/i })).toHaveAttribute(
      'aria-expanded',
      'false'
    );
  });

  it('points aria-controls at the panel it toggles', async () => {
    const user = userEvent.setup();

    renderBox({
      examples: [{ label: 'CSV example', content: <p>name,email</p> }],
    });

    const toggle = screen.getByRole('button', { name: /CSV example/i });
    const panelId = toggle.getAttribute('aria-controls');

    expect(panelId).toBeTruthy();
    expect(document.getElementById(panelId)).toBeNull();

    await user.click(toggle);

    expect(document.getElementById(panelId)).toHaveTextContent('name,email');
  });

  it('labels a sample and keeps its content verbatim', () => {
    render(
      <FormatInfoSample label="engineering.csv">{`name,email
Aarti Rao,aarti@example.com`}</FormatInfoSample>
    );

    expect(screen.getByText('engineering.csv')).toBeInTheDocument();
    expect(
      screen.getByText(/Aarti Rao,aarti@example\.com/)
    ).toBeInTheDocument();
  });
});