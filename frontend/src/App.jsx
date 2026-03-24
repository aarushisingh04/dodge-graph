import React, { useCallback, useEffect, useMemo, useState } from 'react'
import ChatPanel from './components/ChatPanel.jsx'
import GraphCanvas from './components/GraphCanvas.jsx'
import logoSrc from '../../dodge_logo.jpg'

const SUGGESTIONS = [
  'Which products are associated with the highest number of billing documents?',
  'Trace the full flow of billing document 90504259',
  'Show me sales orders that were delivered but not billed',
  'Which customers have the most sales orders?',
  'What is the total billed amount per customer?',
  'Show billing documents that are cancelled',
  'Which plants ship the most deliveries?'
]

export default function App() {
  const [graphData, setGraphData] = useState({ nodes: [], links: [] })
  const [selectedNode, setSelectedNode] = useState(null)
  const [highlightNodes, setHighlightNodes] = useState(new Set())
  const [loading, setLoading] = useState(true)

  const nodeLookup = useMemo(
    () =>
      new Map(
        (graphData.nodes || []).map((node) => [
          node.id,
          {
            id: node.id,
            label: node.label,
            type: node.type
          }
        ])
      ),
    [graphData]
  )

  useEffect(() => {
    fetch('/api/graph')
      .then((response) => response.json())
      .then((data) => {
        setGraphData(data)
        setLoading(false)
      })
      .catch((error) => {
        console.error(error)
        setLoading(false)
      })

  }, [])

  const handleNodeClick = useCallback((node) => {
    setSelectedNode(node)
    fetch(`/api/node/${encodeURIComponent(node.id)}`)
      .then((response) => response.json())
      .then((detail) => {
        const connected = new Set([node.id, ...detail.connections.map((connection) => connection.id)])
        setHighlightNodes(connected)
        setSelectedNode({ ...node, detail })
      })
      .catch(console.error)
  }, [])

  const handleHighlightFromChat = useCallback(
    (nodeIds, primaryNodeId = null) => {
      const nextHighlightNodes = new Set(nodeIds.filter((nodeId) => nodeLookup.has(nodeId)))
      setHighlightNodes(nextHighlightNodes)

      if (primaryNodeId && nodeLookup.has(primaryNodeId)) {
        handleNodeClick(nodeLookup.get(primaryNodeId))
        return
      }

      setSelectedNode(null)
    },
    [handleNodeClick, nodeLookup]
  )

  return (
    <div className='app-shell'>
      <header className='app-header'>
        <img className='brand-mark' src={logoSrc} alt='Dodge logo' />
        <div className='title-group'>
          <div className='eyebrow'>Mapping / Order to Cash</div>
          <h1>o2c graph workspace</h1>
        </div>
      </header>

      <div className='main-layout'>
        <div className='graph-panel'>
          {loading ? (
            <div className='loading-state'>Loading graph...</div>
          ) : (
            <GraphCanvas
              graphData={graphData}
              onNodeClick={handleNodeClick}
              selectedNode={selectedNode}
              highlightNodes={highlightNodes}
              onDeselectNode={() => {
                setSelectedNode(null)
                setHighlightNodes(new Set())
              }}
            />
          )}
        </div>

        <ChatPanel
          suggestions={SUGGESTIONS}
          onHighlightNodes={handleHighlightFromChat}
          nodeLookup={nodeLookup}
        />
      </div>
    </div>
  )
}
