import { useEffect, useRef, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { nextId, updateMemory } from '../../mock/api'
import { AUDIT_THOUGHTS } from '../../mock/data'
import type { CharacterInfo } from '../../types'
import { cn } from '../../utils/cn'
import { Avatar } from '../common/Avatar'
import { MemoryListView } from './MemoryListView'

// 记忆整理 Tab（§7.4）：默认对话式整理，右上角切换列表视图。
// 对话流程：角色抛出「思考」→ 用户回应 → 角色给出修正提案 → 用户确认 → 写入记忆系统。

const CONFIRM_PATTERN = /确认|好|可以|同意|ok/i

interface AuditMessage {
  id: string
  role: 'user' | 'character'
  content: string
  /** 角色的「思考」：用特殊样式与普通对话区分 */
  thought?: boolean
}

type Stage = 'idle' | 'awaitingConfirm' | 'done'

export function MemoryTab({ character }: { character: CharacterInfo }) {
  const [view, setView] = useState<'chat' | 'list'>('chat')

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-stage-700 px-6 py-2.5">
        <span className="text-xs text-stone-500">
          {view === 'chat'
            ? '对话式整理：回应角色的思考，确认后写入记忆系统'
            : '列表视图：编辑、删除、调整重要性，拖拽可合并'}
        </span>
        <button
          onClick={() => setView((v) => (v === 'chat' ? 'list' : 'chat'))}
          className="rounded border border-stage-600 px-3 py-1 text-xs text-stone-300 hover:border-gold hover:text-gold"
        >
          {view === 'chat' ? '☰ 列表视图' : '💬 对话视图'}
        </button>
      </div>
      {view === 'chat' ? <AuditConversation character={character} /> : <MemoryListView character={character} />}
    </div>
  )
}

function AuditConversation({ character }: { character: CharacterInfo }) {
  const audit = AUDIT_THOUGHTS[character.id]
  const [messages, setMessages] = useState<AuditMessage[]>(() => [
    {
      id: nextId('audit'),
      role: 'character',
      content: audit ? audit.thought : '（这位角色的记忆系统今天很安静，没有要整理的东西。）',
      thought: true,
    },
  ])
  const [input, setInput] = useState('')
  const [stage, setStage] = useState<Stage>('idle')
  const [replying, setReplying] = useState(false)
  const [feedback, setFeedback] = useState<string | null>(null)
  const timers = useRef<ReturnType<typeof setTimeout>[]>([])
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => () => timers.current.forEach(clearTimeout), [])

  // 操作反馈条：几秒后自动消失
  useEffect(() => {
    if (feedback === null) return
    const t = setTimeout(() => setFeedback(null), 4000)
    return () => clearTimeout(t)
  }, [feedback])

  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, replying])

  const replyLater = (content: string) => {
    setReplying(true)
    timers.current.push(
      setTimeout(
        () => {
          setMessages((prev) => [...prev, { id: nextId('audit'), role: 'character', content }])
          setReplying(false)
        },
        600 + Math.random() * 400,
      ),
    )
  }

  const send = () => {
    const content = input.trim()
    if (!content || replying) return
    setMessages((prev) => [...prev, { id: nextId('audit'), role: 'user', content }])
    setInput('')

    if (!audit) {
      replyLater('我今天想不出要整理什么。要不切到列表视图，直接帮我看看？')
      return
    }

    if (stage === 'idle') {
      setStage('awaitingConfirm')
      replyLater(audit.proposal)
      return
    }

    if (stage === 'awaitingConfirm') {
      if (CONFIRM_PATTERN.test(content)) {
        setStage('done')
        void updateMemory(audit.memoryId, { content: audit.newContent }).then(() =>
          setFeedback(`✅ 已更新记忆条目 ${audit.memoryId}`),
        )
        replyLater('好，那就这么改了。这条记忆现在更贴近真相了。')
      } else {
        replyLater(`嗯，也许我没说清楚。我想把它改成：「${audit.newContent}」——这样更准确。如果同意，回复「确认」我就写进去。`)
      }
      return
    }

    replyLater('这条记忆已经整理好了。想继续的话，右上角切到列表视图，那里可以编辑、合并、删除。')
  }

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto px-6 py-5">
        {messages.map((msg) =>
          msg.thought ? (
            <motion.div
              key={msg.id}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              className="rounded-lg border border-dashed border-stage-600 bg-stage-900 px-4 py-3"
            >
              <div className="mb-1 text-xs text-stone-500">💭 {character.name} 正在整理自己的记忆…</div>
              <p className="font-mono text-sm leading-relaxed text-stone-300">{msg.content}</p>
            </motion.div>
          ) : msg.role === 'user' ? (
            <motion.div key={msg.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="flex justify-end">
              <div className="max-w-[70%] rounded-lg rounded-br-none bg-stage-700 px-3.5 py-2.5 text-sm leading-relaxed text-stone-200">
                {msg.content}
              </div>
            </motion.div>
          ) : (
            <motion.div key={msg.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="flex items-end gap-2">
              <Avatar name={character.name} color={character.color} size={28} />
              <div
                className="max-w-[70%] rounded-lg rounded-bl-none border border-stage-700 bg-stage-800 px-3.5 py-2.5 font-serif text-sm leading-relaxed text-stone-100"
                style={{ borderLeft: `3px solid ${character.color}` }}
              >
                {msg.content}
              </div>
            </motion.div>
          ),
        )}

        {replying && (
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

      <div className="border-t border-stage-700 px-6 py-3">
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
            placeholder={cn('回应 ta 的思考…', stage === 'awaitingConfirm' && '（回复「确认」即可写入）')}
            className="flex-1 resize-none rounded-lg border border-stage-600 bg-stage-900 px-3 py-2 text-sm text-stone-200 outline-none placeholder:text-stone-600 focus:border-gold"
          />
          <button
            onClick={send}
            disabled={!input.trim() || replying}
            className="rounded-lg bg-gold px-4 py-2 text-sm font-medium text-stage-950 transition-opacity disabled:opacity-40"
          >
            发送
          </button>
        </div>
      </div>

      {/* 操作反馈条 */}
      <AnimatePresence>
        {feedback && (
          <motion.div
            initial={{ opacity: 0, y: 12, x: '-50%' }}
            animate={{ opacity: 1, y: 0, x: '-50%' }}
            exit={{ opacity: 0, y: 12, x: '-50%' }}
            className="absolute bottom-24 left-1/2 z-10 rounded-full border border-gold/40 bg-stage-800 px-4 py-2 font-mono text-xs text-gold shadow-lg"
          >
            {feedback}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
