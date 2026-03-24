import React, { useEffect, useRef, useState } from 'react'

export default function NodeDetail({ node, onClose, onToggleChildren, areChildrenCollapsed = false }) {
  const detail = node.detail
  const props = node.properties || {}
  const retractableConnections =
    detail?.connections?.filter(
      (connection) => connection.direction === 'outgoing' && connection.relation === 'HAS_ITEM'
    ) || []
  const panelRef = useRef(null)
  const dragStateRef = useRef(null)
  const [position, setPosition] = useState(null)

  const displayProps = Object.entries(props).filter(
    ([key, value]) => value && !['type', 'label', 'color'].includes(key) && String(value).length < 80
  )

  useEffect(() => {
    setPosition(null)
  }, [node.id])

  useEffect(() => {
    const handlePointerMove = (event) => {
      const dragState = dragStateRef.current
      const panel = panelRef.current
      if (!dragState || !panel) {
        return
      }

      const nextLeft = event.clientX - dragState.offsetX
      const nextTop = event.clientY - dragState.offsetY
      const maxLeft = Math.max(0, window.innerWidth - panel.offsetWidth)
      const maxTop = Math.max(0, window.innerHeight - panel.offsetHeight)

      setPosition({
        left: Math.min(Math.max(0, nextLeft), maxLeft),
        top: Math.min(Math.max(0, nextTop), maxTop)
      })
    }

    const handlePointerUp = () => {
      dragStateRef.current = null
    }

    window.addEventListener('pointermove', handlePointerMove)
    window.addEventListener('pointerup', handlePointerUp)

    return () => {
      window.removeEventListener('pointermove', handlePointerMove)
      window.removeEventListener('pointerup', handlePointerUp)
    }
  }, [])

  const handlePointerDown = (event) => {
    if (event.target.closest('button')) {
      return
    }

    const panel = panelRef.current
    if (!panel) {
      return
    }

    const rect = panel.getBoundingClientRect()
    dragStateRef.current = {
      offsetX: event.clientX - rect.left,
      offsetY: event.clientY - rect.top
    }
  }

  return (
    <div
      ref={panelRef}
      className='node-detail'
      style={
        position
          ? {
              left: `${position.left}px`,
              top: `${position.top}px`,
              transform: 'none'
            }
          : undefined
      }
    >
      <div className='node-detail-header node-detail-drag-handle' onPointerDown={handlePointerDown}>
        <div>
          <div className='type-badge'>{node.type.replace(/([A-Z])/g, ' $1').trim()}</div>
          <h3>{node.label}</h3>
        </div>
        <button type='button' className='detail-close' onClick={onClose}>
          Close
        </button>
      </div>

      <div className='node-intro'>
        <span>Entity:</span> {node.type.replace(/([A-Z])/g, ' $1').trim()}
      </div>

      {retractableConnections.length > 0 && (
        <div className='detail-actions'>
          <button type='button' className='detail-action-btn' onClick={() => onToggleChildren(node.id)}>
            {areChildrenCollapsed ? 'Expand children' : 'Retract children'}
          </button>
        </div>
      )}

      {displayProps.slice(0, 12).map(([key, value]) => (
        <div key={key} className='prop-row'>
          <span className='prop-key'>{key}</span>
          <span className='prop-val'>{String(value)}</span>
        </div>
      ))}

      {detail?.connections?.length > 0 && (
        <div className='connections-section'>
          <h4>Connections: {detail.connections.length}</h4>
          {detail.connections.map((connection, index) => (
            <div key={`${connection.id}-${index}`} className='conn-item'>
              <span style={{ fontSize: 8 }}>{connection.direction === 'outgoing' ? '->' : '<-'}</span>
              <span className='conn-relation'>{connection.relation}</span>
              <span className='conn-label'>{connection.label || connection.id}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
