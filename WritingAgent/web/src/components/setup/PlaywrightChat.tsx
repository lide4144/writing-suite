import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { nextId } from '../../mock/api'
import { PLAYWRIGHT_OPENING, PLAYWRIGHT_REPLIES } from '../../mock/data'
import { cn } from '../../utils/cn'

// 编剧对话区（§6.4 左侧）：用户与「编剧 Agent」的 IM 对话。
// 编剧回复来自 PLAYWRIGHT_REPLIES 语料，按序推进；语料用完后停在最后一条（提示可生成草稿）。

export interface PlaywrightDraft {
  /** 递增序号：父组件每次点「生成草稿」时 +1，驱动本组件追加草稿消息 */
  seq: number
  doc: string
}

interface ChatMsg {
  id: string
  role: 'user' | 'playwright'
  content: string
  kind: 'text' | 'draft'
}

interface PlaywrightChatProps {
  draft: PlaywrightDraft | null
  /** 「应用到文档」：text 回复以「编剧笔记」追加（append），草稿消息整篇覆盖（replace） */
  onApplyToDoc: (content: string, mode: 'append' | 'replace') => void
}

export function PlaywrightChat({ draft, onApplyToDoc }: PlaywrightChatProps) {
  const [messages, setMessages] = useState<ChatMsg[]>(() => [
    { id: nextId('pw'), role: 'playwright', content: PLAYWRIGHT_OPENING, kind: 'text' },
  ])
  const [input, setInput] = useState('')
  const [thinking, setThinking] = useState(false)
  const replyCursor = useRef(0)
  const lastDraftSeq = useRef(0)
  const timers = useRef<ReturnType<typeof setTimeout>[]>([])
  const scrollRef = useRef<HTMLDivElement>(null)

  // 父组件点击「生成草稿」：以编剧口吻追加一条包含完整场景文档的消息
  useEffect(() => {
    if (draft && draft.seq !== lastDraftSeq.current) {
      lastDraftSeq.current = draft.seq
      setMessages((prev) => [...prev, { id: nextId('pw'), role: 'playwright', content: draft.doc, kind: 'draft' }])
    }
  }, [draft])

  useEffect(() => () => timers.current.forEach(clearTimeout), [])

  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, thinking])

  const send = () => {
    const content = input.trim()
    if (!content || thinking) return
    setMessages((prev) => [...prev, { id: nextId('pw'), role: 'user', content, kind: 'text' }])
    setInput('')
    setThinking(true)
    timers.current.push(
      setTimeout(
        () => {
          const text = PLAYWRIGHT_REPLIES[Math.min(replyCursor.current, PLAYWRIGHT_REPLIES.length - 1)]
          replyCursor.current += 1
          setMessages((prev) => [...prev, { id: nextId('pw'), role: 'playwright', content: text, kind: 'text' }])
          setThinking(false)
        },
        800 + Math.random() * 700,
      ),
    )
  }

  return (
    <div className="flex h-full flex-col rounded-lg border border-stage-700 bg-stage-900">
      <header className="border-b border-stage-700 px-4 py-3">
        <div className="text-sm font-medium text-stone-100">✍️ 编剧</div>
        <div className="mt-0.5 text-xs text-stone-500">和他讨论这场戏的方向，回复可以应用到右侧文档</div>
      </header>

      <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {messages.map((msg) => (
          <motion.div
            key={msg.id}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            className={cn('flex', msg.role === 'user' ? 'justify-end' : 'justify-start')}
          >
            {msg.role === 'user' ? (
              <div className="max-w-[85%] rounded-lg rounded-br-none bg-stage-700 px-3.5 py-2.5 text-sm leading-relaxed text-stone-200">
                {msg.content}
              </div>
            ) : (
              <div className="max-w-[92%] rounded-lg rounded-bl-none border border-stage-700 bg-stage-800 px-3.5 py-2.5">
                <div className="mb-1 flex items-center justify-between gap-3">
                  <span className="text-xs text-gold/80">{msg.kind === 'draft' ? '📋 场景文档草稿' : '编剧'}</span>
                  <button
                    onClick={() => onApplyToDoc(msg.content, msg.kind === 'draft' ? 'replace' : 'append')}
                    className="rounded border border-stage-600 px-1.5 py-0.5 text-[11px] text-stone-500 transition-colors hover:border-gold hover:text-gold"
                  >
                    应用到文档
                  </button>
                </div>
                {msg.kind === 'draft' ? (
                  <pre className="max-h-56 overflow-auto whitespace-pre-wrap rounded bg-stage-950/70 p-2.5 font-mono text-xs leading-relaxed text-stone-300">
                    {msg.content}
                  </pre>
                ) : (
                  <p className="text-sm leading-relaxed text-stone-200">{msg.content}</p>
                )}
              </div>
            )}
          </motion.div>
        ))}

        {thinking && (
          <div className="flex justify-start">
            <div className="flex items-center gap-1 rounded-lg rounded-bl-none border border-stage-700 bg-stage-800 px-3.5 py-3">
              <span className="typing-dot inline-block h-1.5 w-1.5 rounded-full bg-stone-400" />
              <span className="typing-dot inline-block h-1.5 w-1.5 rounded-full bg-stone-400" />
              <span className="typing-dot inline-block h-1.5 w-1.5 rounded-full bg-stone-400" />
            </div>
          </div>
        )}
      </div>

      <div className="border-t border-stage-700 p-3">
        <div className="flex items-end gap-2">
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
            placeholder="说说你的想法：谁和谁、在哪里、气氛如何…"
            className="flex-1 resize-none rounded-lg border border-stage-600 bg-stage-950 px-3 py-2 text-sm text-stone-200 outline-none placeholder:text-stone-600 focus:border-gold"
          />
          <button
            onClick={send}
            disabled={!input.trim() || thinking}
            className="rounded-lg bg-gold px-4 py-2 text-sm font-medium text-stage-950 transition-opacity disabled:opacity-40"
          >
            发送
          </button>
        </div>
      </div>
    </div>
  )
}
