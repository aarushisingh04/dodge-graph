import React, { useState } from 'react'

export default function ChatMessage({ msg, onHighlightNodes }) {
  const [showSql, setShowSql] = useState(false)

  return (
    <div className={`msg ${msg.role}`}>
      <div className='msg-meta'>
        <div className={`msg-avatar ${msg.role}`}>{msg.role === 'assistant' ? 'D' : 'Y'}</div>
        <div>
          <div className='msg-author'>{msg.role === 'assistant' ? 'Dodge AI' : 'You'}</div>
          <div className='msg-role-label'>{msg.role === 'assistant' ? 'Graph Agent' : 'Operator'}</div>
        </div>
      </div>
      <div className='msg-bubble'>{msg.content}</div>
      {msg.sql && (
        <>
          <div className='sql-toggle' onClick={() => setShowSql((value) => !value)}>
            {showSql ? 'Hide SQL' : 'Show SQL'}
          </div>
          {showSql && <div className='msg-sql'>{msg.sql}</div>}
        </>
      )}
      {msg.results?.length > 0 && <div className='msg-results'>{msg.results.length} row(s) returned</div>}
      {msg.trace?.steps?.length > 0 && <TraceCard trace={msg.trace} onHighlightNodes={onHighlightNodes} />}
      {msg.references?.length > 0 && (
        <div className='msg-reference-block'>
          <div className='msg-reference-header'>
            <span>Referenced nodes</span>
            <button
              type='button'
              className='msg-reference-action'
              onClick={() => onHighlightNodes(msg.references.map((reference) => reference.id))}
            >
              Highlight all
            </button>
          </div>
          <div className='msg-reference-list'>
            {msg.references.map((reference) => (
              <button
                key={reference.id}
                type='button'
                className='msg-reference-chip'
                onClick={() => onHighlightNodes([reference.id], reference.id)}
              >
                <span className='msg-reference-type'>{reference.type}</span>
                <span className='msg-reference-label'>{reference.label}</span>
                {reference.value !== reference.label && (
                  <span className='msg-reference-id'>{reference.value}</span>
                )}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function TraceCard({ trace, onHighlightNodes }) {
  const traceReferences = trace.steps
    .filter((step) => step.reference)
    .map((step) => step.reference)

  return (
    <div className='msg-trace-card'>
      <div className='msg-trace-header'>
        <div>
          <div className='msg-trace-title'>Flow trace</div>
          <div className='msg-trace-subtitle'>
            {trace.requestedEntityType} {trace.requestedValue}
          </div>
        </div>
        {traceReferences.length > 0 && (
          <button
            type='button'
            className='msg-reference-action'
            onClick={() => onHighlightNodes(traceReferences.map((reference) => reference.id))}
          >
            Highlight path
          </button>
        )}
      </div>

      <div className='msg-trace-steps'>
        {trace.steps.map((step) => (
          <button
            key={step.name}
            type='button'
            className={`msg-trace-step ${step.status}`}
            disabled={!step.reference}
            onClick={() => step.reference && onHighlightNodes([step.reference.id], step.reference.id)}
          >
            <span className='msg-trace-step-name'>{step.name}</span>
            <span className='msg-trace-step-value'>
              {step.reference ? step.reference.label : 'Missing in this flow'}
            </span>
          </button>
        ))}
      </div>
    </div>
  )
}
