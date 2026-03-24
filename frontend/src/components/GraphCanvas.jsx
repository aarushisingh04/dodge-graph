import React, { useCallback, useEffect, useRef, useState } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import NodeDetail from './NodeDetail.jsx'

const TYPE_COLORS = {
  SalesOrder: '#5f57d8',
  SalesOrderItem: '#897ff0',
  Delivery: '#4f87d9',
  DeliveryItem: '#82ace8',
  BillingDoc: '#283041',
  BillingItem: '#68758b',
  JournalEntry: '#6b52d9',
  Payment: '#b8aaf5',
  Customer: '#374255',
  Product: '#7a6ce6',
  Plant: '#9ca6ba'
}

const NODE_SIZES = {
  SalesOrder: 8,
  Delivery: 8,
  BillingDoc: 8,
  JournalEntry: 7,
  Payment: 6,
  SalesOrderItem: 4,
  DeliveryItem: 4,
  BillingItem: 4,
  Customer: 9,
  Product: 6,
  Plant: 6
}

const LEGEND_ITEMS = Object.entries(TYPE_COLORS)
const CHAT_HIGHLIGHT_COLOR = '#ff7a18'
const RETRACTABLE_RELATIONS = new Set(['HAS_ITEM'])

function cloneGraphData(graphData) {
  return {
    nodes: (graphData?.nodes || []).map(({ id, label, type, color, properties, detail }) => ({
      id,
      label,
      type,
      color,
      properties,
      detail
    })),
    links: (graphData?.links || []).map(({ source, target, relation }) => ({
      source: typeof source === 'object' ? source.id : source,
      target: typeof target === 'object' ? target.id : target,
      relation
    }))
  }
}

function preserveNodeLayout(nextGraph, previousGraphData) {
  if (!previousGraphData?.nodes?.length) {
    return nextGraph
  }

  const previousNodeMap = new Map(previousGraphData.nodes.map((node) => [node.id, node]))

  return {
    ...nextGraph,
    nodes: nextGraph.nodes.map((node) => {
      const previousNode = previousNodeMap.get(node.id)
      if (!previousNode) {
        return node
      }

      return {
        ...node,
        x: previousNode.x,
        y: previousNode.y,
        vx: previousNode.vx,
        vy: previousNode.vy,
        fx: previousNode.fx,
        fy: previousNode.fy
      }
    })
  }
}

function buildCollapsedGraphData(graphData, collapsedNodeIds, previousGraphData = null) {
  const baseGraph = cloneGraphData(graphData)

  if (collapsedNodeIds.size === 0) {
    return preserveNodeLayout(baseGraph, previousGraphData)
  }

  const outgoingRetractableLinks = new Map()
  baseGraph.links.forEach((link) => {
    if (!RETRACTABLE_RELATIONS.has(link.relation)) {
      return
    }

    const sourceLinks = outgoingRetractableLinks.get(link.source) || []
    sourceLinks.push(link)
    outgoingRetractableLinks.set(link.source, sourceLinks)
  })

  const hiddenNodeIds = new Set()

  collapsedNodeIds.forEach((nodeId) => {
    const stack = [...(outgoingRetractableLinks.get(nodeId) || [])]

    while (stack.length > 0) {
      const link = stack.pop()
      if (hiddenNodeIds.has(link.target)) {
        continue
      }

      hiddenNodeIds.add(link.target)
      const nestedLinks = outgoingRetractableLinks.get(link.target) || []
      nestedLinks.forEach((nestedLink) => {
        stack.push(nestedLink)
      })
    }
  })

  collapsedNodeIds.forEach((nodeId) => {
    hiddenNodeIds.delete(nodeId)
  })

  return preserveNodeLayout(
    {
    nodes: baseGraph.nodes.filter((node) => !hiddenNodeIds.has(node.id)),
    links: baseGraph.links.filter(
      (link) => !hiddenNodeIds.has(link.source) && !hiddenNodeIds.has(link.target)
    )
    },
    previousGraphData
  )
}

export default function GraphCanvas({
  graphData,
  onNodeClick,
  selectedNode,
  highlightNodes,
  onDeselectNode
}) {
  const graphRef = useRef(null)
  const containerRef = useRef(null)
  const [size, setSize] = useState({ width: 0, height: 0 })
  const [showOverlay, setShowOverlay] = useState(true)
  const [graphInstanceKey, setGraphInstanceKey] = useState(0)
  const [collapsedNodeIds, setCollapsedNodeIds] = useState(new Set())
  const [renderGraphData, setRenderGraphData] = useState(() => cloneGraphData(graphData))

  useEffect(() => {
    setRenderGraphData((current) => buildCollapsedGraphData(graphData, collapsedNodeIds, current))
  }, [graphData, collapsedNodeIds])

  useEffect(() => {
    if (!graphRef.current || highlightNodes.size === 0) {
      return
    }

    const highlightedIds = new Set(highlightNodes)
    const timer = window.setTimeout(() => {
      graphRef.current?.zoomToFit?.(500, 110, (node) => highlightedIds.has(node.id))
    }, 120)

    return () => window.clearTimeout(timer)
  }, [highlightNodes, renderGraphData])

  useEffect(() => {
    if (!containerRef.current) {
      return
    }

    const updateSize = () => {
      const rect = containerRef.current.getBoundingClientRect()
      setSize({
        width: Math.max(0, Math.floor(rect.width)),
        height: Math.max(0, Math.floor(rect.height))
      })
    }

    updateSize()

    const observer = new ResizeObserver(updateSize)
    observer.observe(containerRef.current)
    window.addEventListener('resize', updateSize)

    return () => {
      observer.disconnect()
      window.removeEventListener('resize', updateSize)
    }
  }, [])

  const nodeCanvasObject = useCallback(
    (node, ctx, globalScale) => {
      const size = NODE_SIZES[node.type] || 5
      const isHighlighted = highlightNodes.size === 0 || highlightNodes.has(node.id)
      const isChatHighlighted = highlightNodes.has(node.id)
      const color = node.color || '#7e8394'

      ctx.beginPath()
      ctx.arc(node.x, node.y, size + 2, 0, 2 * Math.PI)
      ctx.fillStyle = isHighlighted ? `${color}22` : `${color}14`
      ctx.fill()

      ctx.beginPath()
      ctx.arc(node.x, node.y, size, 0, 2 * Math.PI)
      ctx.fillStyle = isChatHighlighted ? CHAT_HIGHLIGHT_COLOR : isHighlighted ? `${color}2d` : `${color}18`
      ctx.fill()
      ctx.lineWidth = isChatHighlighted ? 2.5 : 1.35
      ctx.strokeStyle = isChatHighlighted ? '#ffffff' : isHighlighted ? color : `${color}70`
      ctx.stroke()

      if (isChatHighlighted) {
        ctx.beginPath()
        ctx.arc(node.x, node.y, size + 4, 0, 2 * Math.PI)
        ctx.strokeStyle = `${CHAT_HIGHLIGHT_COLOR}75`
        ctx.lineWidth = 2
        ctx.stroke()
      }

      if (globalScale > 1.5 || isChatHighlighted) {
        const label = node.label?.length > 16 ? `${node.label.slice(0, 14)}...` : node.label
        const fontSize = Math.max(3, 12 / globalScale)
        ctx.font = `500 ${fontSize}px Inter, sans-serif`
        ctx.fillStyle = isChatHighlighted ? '#1d2431' : isHighlighted ? '#31384a' : '#6f789080'
        ctx.textAlign = 'center'
        ctx.fillText(label, node.x, node.y + size + fontSize)
      }
    },
    [highlightNodes]
  )

  const linkColor = useCallback(
    (link) => {
      if (highlightNodes.size === 0) {
        return '#ccd6f0'
      }

      const srcHighlighted = highlightNodes.size === 0 || highlightNodes.has(link.source?.id || link.source)
      const dstHighlighted = highlightNodes.size === 0 || highlightNodes.has(link.target?.id || link.target)
      return srcHighlighted && dstHighlighted ? '#ffb27a' : '#d2d9ea66'
    },
    [highlightNodes]
  )

  const resetGraphView = useCallback(() => {
    setGraphInstanceKey((value) => value + 1)
    setRenderGraphData(cloneGraphData(graphData))
    setCollapsedNodeIds(new Set())
    onDeselectNode()
  }, [graphData, onDeselectNode])

  const zoomIn = useCallback(() => {
    if (graphRef.current) {
      graphRef.current.zoom(graphRef.current.zoom() * 1.2, 250)
    }
  }, [])

  const zoomOut = useCallback(() => {
    if (graphRef.current) {
      graphRef.current.zoom(graphRef.current.zoom() / 1.2, 250)
    }
  }, [])

  const handleToggleNodeChildren = useCallback((nodeId) => {
    setCollapsedNodeIds((current) => {
      const next = new Set(current)
      if (next.has(nodeId)) {
        next.delete(nodeId)
      } else {
        next.add(nodeId)
      }
      return next
    })
  }, [])

  return (
    <div ref={containerRef} className='graph-canvas-wrap'>
      <div className='graph-toolbar'>
        <button type='button' className='toolbar-btn toolbar-btn-secondary' onClick={resetGraphView}>
          Reset View
        </button>
        <button
          type='button'
          className='toolbar-btn toolbar-btn-primary'
          onClick={() => setShowOverlay((value) => !value)}
        >
          {showOverlay ? 'Hide Granular Overlay' : 'Show Granular Overlay'}
        </button>
        {highlightNodes.size > 0 && (
          <div className='graph-focus-chip'>{highlightNodes.size} node(s) highlighted</div>
        )}
      </div>

      <div className='graph-zoom-controls'>
        <button type='button' className='zoom-btn' onClick={zoomIn} aria-label='Zoom in'>
          +
        </button>
        <button type='button' className='zoom-btn' onClick={zoomOut} aria-label='Zoom out'>
          -
        </button>
      </div>

      {size.width > 0 && size.height > 0 && (
        <ForceGraph2D
          key={graphInstanceKey}
          ref={graphRef}
          width={size.width}
          height={size.height}
          graphData={renderGraphData}
          nodeCanvasObject={nodeCanvasObject}
          nodeCanvasObjectMode={() => 'replace'}
          linkColor={linkColor}
          linkWidth={(link) =>
            highlightNodes.size === 0
              ? 0.45
              : highlightNodes.has(link.source?.id || link.source) &&
                  highlightNodes.has(link.target?.id || link.target)
                ? 1.6
                : 0.45
          }
          linkDirectionalArrowLength={3}
          linkDirectionalArrowRelPos={1}
          onNodeClick={onNodeClick}
          onBackgroundClick={onDeselectNode}
          backgroundColor='#f6f5fc'
          cooldownTicks={100}
          d3AlphaDecay={0.02}
          d3VelocityDecay={0.3}
        />
      )}

      {showOverlay && (
        <>
          <div className='legend'>
            <div className='legend-header'>
              <span>Graph Overlay</span>
              <button type='button' className='legend-clear' onClick={onDeselectNode}>
                Clear focus
              </button>
            </div>
            {LEGEND_ITEMS.map(([type, color]) => (
              <div key={type} className='legend-item'>
                <div className='legend-dot' style={{ background: color, boxShadow: `0 0 0 4px ${color}22` }} />
                <span>{type.replace(/([A-Z])/g, ' $1').trim()}</span>
              </div>
            ))}
          </div>

          {selectedNode && (
            <NodeDetail
              node={selectedNode}
              onClose={onDeselectNode}
              onToggleChildren={handleToggleNodeChildren}
              areChildrenCollapsed={collapsedNodeIds.has(selectedNode.id)}
            />
          )}
        </>
      )}
    </div>
  )
}
