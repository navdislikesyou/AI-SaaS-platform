/**
 * A compact, collapsible context box for file format guidance.
 *
 * Every assistant that accepts a file needs the same three things stated:
 * what the backend actually accepts, what it merely recommends, and what will
 * be rejected. This component carries that copy so the three pages stay
 * visually consistent, and so a format rule is written in exactly one place
 * instead of being reworded per page.
 *
 * It is presentation only. It never validates, uploads, or transforms a file.
 */

import { useState } from 'react';
import { ChevronDown, Info } from 'lucide-react';

/**
 * One collapsible example, collapsed by default so the box stays compact.
 *
 * @param {{label: string, accent: string, accentRgb: string, id: string}} props
 * @param {React.ReactNode} props.children The example body, usually a <pre>.
 * @returns {React.ReactElement}
 */
function FormatInfoExample({ label, accent, accentRgb, id, children }) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div style={{ marginTop: '8px' }}>
      <button
        type="button"
        onClick={() => setIsOpen((open) => !open)}
        aria-expanded={isOpen}
        aria-controls={id}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '6px',
          background: 'transparent',
          border: 'none',
          padding: '2px 0',
          cursor: 'pointer',
          fontSize: '0.72rem',
          fontWeight: 500,
          color: accent,
        }}
      >
        <ChevronDown
          size={13}
          style={{
            flexShrink: 0,
            transform: isOpen ? 'rotate(0deg)' : 'rotate(-90deg)',
            transition: 'transform 0.15s ease',
          }}
        />
        <span>{isOpen ? `Hide ${label}` : label}</span>
      </button>

      {isOpen && (
        <div
          id={id}
          style={{
            marginTop: '8px',
            padding: '10px 12px',
            borderRadius: '6px',
            background: 'rgba(0,0,0,0.35)',
            border: `1px solid rgba(${accentRgb}, 0.18)`,
          }}
        >
          {children}
        </div>
      )}
    </div>
  );
}

/**
 * Render a format guidance box for an assistant page.
 *
 * @param {object} props
 * @param {string} props.title Box heading, e.g. "Preparing your document".
 * @param {string} props.accent Hex accent of the agent, e.g. "#E8FF72".
 * @param {string} props.accentRgb The same accent as "r, g, b", for rgba() tints.
 * @param {Array<{label: string, content: React.ReactNode}>} [props.examples]
 *   Collapsible examples, rendered under the body in the order given.
 * @param {React.ReactNode} props.children The box body.
 * @returns {React.ReactElement}
 */
export default function FormatInfoBox({
  title,
  accent,
  accentRgb,
  examples = [],
  children,
}) {
  return (
    <div
      className="saas-info-box"
      style={{
        background: `rgba(${accentRgb}, 0.05)`,
        borderColor: `rgba(${accentRgb}, 0.22)`,
      }}
    >
      <div className="saas-info-box-head">
        <Info size={14} color={accent} style={{ flexShrink: 0 }} />
        <span className="saas-info-box-title" style={{ color: accent }}>
          {title}
        </span>
      </div>

      <div className="saas-info-box-body">{children}</div>

      {examples.map((example, index) => (
        <FormatInfoExample
          key={example.label}
          id={`saas-info-example-${index}`}
          label={example.label}
          accent={accent}
          accentRgb={accentRgb}
        >
          {example.content}
        </FormatInfoExample>
      ))}
    </div>
  );
}

/**
 * A code sample sized for an info box: scrollable rather than wrapping, so a
 * long header row stays one line and does not stretch the card on mobile.
 *
 * @param {{label: string, children: string}} props
 * @returns {React.ReactElement}
 */
export function FormatInfoSample({ label, children }) {
  return (
    <div>
      <div
        style={{
          fontSize: '0.68rem',
          fontFamily: "'JetBrains Mono', monospace",
          textTransform: 'uppercase',
          letterSpacing: '0.04em',
          color: 'rgba(255,255,255,0.45)',
          marginBottom: '6px',
        }}
      >
        {label}
      </div>
      <pre
        style={{
          margin: 0,
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: '0.72rem',
          lineHeight: 1.6,
          color: '#e4e4e7',
          whiteSpace: 'pre',
          overflowX: 'auto',
        }}
      >
        {children}
      </pre>
    </div>
  );
}