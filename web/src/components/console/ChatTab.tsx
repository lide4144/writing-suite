import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { appendChatMessage, getChatHistory, nextId } from '../../mock/api'
import { connectChatSocket, type ChatSocketHandle } from '../../mock/ws'
import type { CharacterInfo, ChatMessage } from '../../types'
import { cn } from '../../utils/cn'
import { Avatar } from '../common/Avatar'

// 聊天 Tab（§7.4）：气泡对话，角色回复经 mock WebSocket 流式返回。
// 「🎭 4th Wall」开关（默认开）：开 = 角色知道你是作者；关 = 角色在戏里。
// 注：回复事件不携带消息 id，并发两条流会互相覆盖，因此回复进行中禁止再次发送。

interface ChatTabProps {
  character: CharacterInfo
}

export function ChatTab({ character }: ChatTabProps) {
  const [messages, setMessages] = useState<ChatMessage[] | null>(null)
  const [input, setInput] = useState('')
  const [fourthWall, setFourthWall] = useState(true)
  const [awaiting, setAwaiting] = useState(false) // 已发送，等待角色开始回复（打字指示器）
  const [streaming, setStreaming] = useState<string | null>(null) // 流式中的角色回复（累计文本）
  const socketRef = useRef<ChatSocketHandle | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let cancelled = false
    getChatHistory(character.id).then((history) => {
      if (!cancelled) setMessages(history)
    })
    return () => {
      cancelled = true
    }
  }, [character.id])

  // 每个角色一条 socket；组件卸载（含切角色 remount）时关闭
  useEffect(() => {
    const socket = connectChatSocket(character.id, (event) => {
      if (event.type !== 'message') return
      setAwaiting(false)
      if (event.data.done) {
        const reply: ChatMessage = {
          id: nextId('chat'),
          characterId: character.id,
          role: 'character',
          content: event.data.content,
          timestamp: new Date().toISOString(),
        }
        appendChatMessage(reply)
        setStreaming(null)
        setMessages((prev) => [...(prev ?? []), reply])
      } else {
        setStreaming(event.data.content)
      }
    })
    socketRef.current = socket
    return () => {
      socket.close()
      socketRef.current = null
    }
  }, [character.id])

  const inFlight = awaiting || streaming !== null

  // 新消息 / 流式推进时滚到底部
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, streaming, awaiting])

  const send = () => {
    const content = input.trim()
    if (!content || inFlight) return
    const userMsg: ChatMessage = {
      id: nextId('chat'),
      characterId: character.id,
      role: 'user',
      content,
      timestamp: new Date().toISOString(),
    }
    appendChatMessage(userMsg)
    setMessages((prev) => [...(prev ?? []), userMsg])
    setInput('')
    setAwaiting(true)
    socketRef.current?.send(content, fourthWall)
  }

  return (
    <div className="flex h-full flex-col">
      <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto px-6 py-5">
        {messages === null ? (
          <p className="text-sm text-stone-500">加载聊天记录…</p>
        ) : messages.length === 0 && !awaiting && streaming === null ? (
          <p className="py-10 text-center text-sm text-stone-500">还没有聊过。说点什么，开场吧。</p>
        ) : (
          messages.map((msg) => <Bubble key={msg.id} msg={msg} character={character} />)
        )}

        {streaming !== null && <CharacterBubble character={character} content={streaming} streaming />}

        {awaiting && (
          <div className="flex items-end gap-2">
            <Avatar name={character.name} color={character.color} size={28} />
            <div className="flex items-center gap-1 rounded-lg rounded-bl-none border border-stage-700 bg-stage-800 px-3.5 py-3">
              <span className="typing-dot inline-block h-1.5 w-1.5 rounded-full bg-stone-400" />
              <span className="typing-dot inline-block h-1.5 w-1.5 rounded-full bg-stone-400" />
              <span className="typing-dot inline-block h-1.5 w-1.5 rounded-full bg-stone-400" />
            </div>
          </div>
        )}
      </div>

      {/* 输入区：右上方第四面墙开关 */}
      <div className="border-t border-stage-700 px-6 pb-5 pt-3">
        <div className="mb-2 flex items-center justify-end gap-2.5">
          <span className="text-xs text-stone-500">
            {fourthWall ? '角色知道你是作者' : '角色在戏里，不知道你的身份'}
          </span>
          <button
            onClick={() => setFourthWall((v) => !v)}
            title="第四面墙：开 = 角色知道你是作者；关 = 角色在戏里"
            className={cn(
              'rounded-full border px-3 py-1 text-xs transition-colors',
              fourthWall
                ? 'border-gold/60 bg-gold/10 text-gold'
                : 'border-stage-600 text-stone-400 hover:border-stone-500',
            )}
          >
            🎭 4th Wall · {fourthWall ? '开' : '关'}
          </button>
        </div>
        <div className="flex items-end gap-3">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault()
                send()
              }
            }}
            rows={2}
            placeholder={fourthWall ? '以作者的身份说点什么…' : '走进戏里，以剧中人的方式开口…'}
            className="flex-1 resize-none rounded-lg border border-stage-600 bg-stage-900 px-3 py-2 text-sm text-stone-200 outline-none placeholder:text-stone-600 focus:border-gold"
          />
          <button
            onClick={send}
            disabled={!input.trim() || inFlight}
            className="rounded-lg bg-gold px-4 py-2 text-sm font-medium text-stage-950 transition-opacity disabled:opacity-40"
          >
            发送
          </button>
        </div>
      </div>
    </div>
  )
}

function Bubble({ msg, character }: { msg: ChatMessage; character: CharacterInfo }) {
  if (msg.role === 'user') {
    return (
      <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="flex justify-end">
        <div className="max-w-[70%] rounded-lg rounded-br-none bg-stage-700 px-3.5 py-2.5 text-sm leading-relaxed text-stone-200">
          {msg.content}
        </div>
      </motion.div>
    )
  }
  return <CharacterBubble character={character} content={msg.content} />
}

/** 角色气泡：角色主题色左边框 + serif 正文 */
function CharacterBubble({
  character,
  content,
  streaming = false,
}: {
  character: CharacterInfo
  content: string
  streaming?: boolean
}) {
  return (
    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="flex items-end gap-2">
      <Avatar name={character.name} color={character.color} size={28} />
      <div
        className="max-w-[70%] rounded-lg rounded-bl-none border border-stage-700 bg-stage-800 px-3.5 py-2.5 font-serif text-sm leading-relaxed text-stone-100"
        style={{ borderLeft: `3px solid ${character.color}` }}
      >
        {content}
        {streaming && <span className="ml-0.5 inline-block h-3.5 w-[3px] animate-pulse bg-gold/70 align-text-bottom" />}
      </div>
    </motion.div>
  )
}
