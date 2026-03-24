import React, { useEffect, useRef, useState } from 'react'
import ChatMessage from './ChatMessage.jsx'
import { extractNodeReferences } from '../lib/chatReferences.js'

const API_BASE = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '')

export default function ChatPanel({ suggestions, onHighlightNodes, nodeLookup }) {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content:
        'Hi! I can help you analyze the Order-to-Cash process. Ask me about sales orders, deliveries, billing documents, payments, or the full flow between them.',
      sql: null,
      results: null,
      references: null
    }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const downloadChatHistory = () => {
    const exportPayload = {
      exportedAt: new Date().toISOString(),
      messageCount: messages.length,
      messages: messages.map((message) => ({
        role: message.role,
        content: message.content,
        sql: message.sql || null,
        results: message.results || null,
        references: message.references || null,
        error: message.error || null
      }))
    }

    const blob = new Blob([JSON.stringify(exportPayload, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-')

    link.href = url
    link.download = `dodge-chat-history-${timestamp}.json`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

  const send = async (text) => {
    const question = (text || input).trim()
    if (!question || loading) {
      return
    }

    const history = messages
      .filter((message) => message.role === 'user' || message.role === 'assistant')
      .map((message) => ({
        role: message.role,
        content: message.content,
        sql: message.sql || null,
        results: message.results || null,
        references: message.references || null
      }))

    setInput('')
    setMessages((prev) => [...prev, { role: 'user', content: question }])
    setLoading(true)

    try {
      const response = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: question, history })
      })
      const data = await response.json()

      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: data.answer,
          sql: data.sql,
          results: data.results,
          error: data.error,
          references: data.references || extractNodeReferences(data.results, nodeLookup),
          trace: data.trace || null,
          explanation: data.explanation || null
        }
      ])

      if (data.results?.length > 0) {
        const nodeIds = (data.references || extractNodeReferences(data.results, nodeLookup)).map(
          (reference) => reference.id
        )
        if (nodeIds.length > 0) {
          onHighlightNodes(nodeIds)
        }
      }
    } catch (error) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: 'Error connecting to the server. Please try again.',
          sql: null,
          results: null,
          references: null,
          trace: null
        }
      ])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className='chat-panel'>
      <div className='chat-header'>
        <div>
          <div className='chat-header-title'>Dodge AI</div>
          <div className='chat-header-subtitle chat-header-status'>
            <span className='status-dot' />
            Active
          </div>
        </div>
        <div className='chat-header-actions'>
          <button type='button' className='chat-download-btn' onClick={downloadChatHistory}>
            Download
          </button>
        </div>
      </div>

      <div className='chat-messages'>
        {messages.map((message, index) => (
          <ChatMessage key={index} msg={message} onHighlightNodes={onHighlightNodes} />
        ))}
        {loading && (
          <div className='msg assistant'>
            <div className='msg-bubble loading-bubble'>
              <div className='loading-dots'>
                <span>.</span>
                <span>.</span>
                <span>.</span>
              </div>
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className='suggested-queries'>
        <p>Suggested prompts</p>
        {suggestions.slice(0, 3).map((suggestion, index) => (
          <button key={index} className='suggestion-chip' onClick={() => send(suggestion)}>
            {suggestion.length > 55 ? `${suggestion.slice(0, 53)}...` : suggestion}
          </button>
        ))}
      </div>

      <div className='chat-input-row'>
        <input
          className='chat-input'
          type='text'
          value={input}
          onChange={(event) => setInput(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              send()
            }
          }}
          placeholder='Analyze anything in the order-to-cash flow'
        />
        <button className='send-btn' onClick={() => send()} disabled={loading || !input.trim()}>
          Analyze
        </button>
      </div>
    </div>
  )
}
