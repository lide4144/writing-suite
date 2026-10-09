// 活动流消息卡片（§5.4.1）：四种类型按徽章与底色区分。
// 台词用衬线体，动作用斜体叙述体；默认只显示对外表现（§8.2）。

import { motion } from 'framer-motion'
import type { Message, MessageType } from '../../types'
import { Avatar } from '../common/Avatar'
import { formatClock } from '../../utils/time'
import { cn } from '../../utils/cn'
import { InnerThoughtToggle } from './InnerThoughtToggle'

const TYPE_META: Record<MessageType, { icon: string; label: string }> = {
  env: { icon: '🎭', label: '环境' },
  npc: { icon: '🎭', label: 'NPC' },
  dialogue: { icon: '💬', label: '对话' },
  action: { icon: '🏃', label: '动作' },
  scene_change: { icon: '🎬', label: '场景' },
}

interface MessageCardProps {
  message: Message
  /** 角色主题色；GM 消息传 GM_COLOR */
  color: string
  highlighted: boolean
  onCharacterEnter: (characterId: string, rect: DOMRect) => void
  onCharacterLeave: (characterId: string) => void
}

export function MessageCard({ message, color, highlighted, onCharacterEnter, onCharacterLeave }: MessageCardProps) {
  const meta = TYPE_META[message.type]
  const characterId = message.characterId
  const isCharacterAct = characterId !== null && (message.type === 'dialogue' || message.type === 'action')

  return (
    <motion.article
      data-mid={message.id}
      className={cn(
        'rounded-xl border px-4 py-3 transition-shadow',
        message.type === 'env' && 'border-stage-700/40 bg-stage-800/50',
        message.type === 'npc' && 'border-stage-700 bg-stage-800',
        message.type === 'scene_change' && 'border-gold/30 bg-gold/10',
        highlighted && 'ring-2 ring-gold/80',
      )}
      style={
        isCharacterAct
          ? { backgroundColor: `${color}14`, borderColor: `${color}45` }
          : undefined
      }
      initial={{ opacity: 0, y: 14 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, ease: 'easeOut' }}
    >
      <header className="flex items-center gap-2">
        {characterId === null ? (
          <>
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-stage-600 text-sm">
              🎭
            </span>
            <span className="text-sm font-medium text-stone-400">{message.characterName}</span>
          </>
        ) : (
          <button
            type="button"
            className="-ml-1 flex items-center gap-2 rounded-md px-1 py-0.5 transition-colors hover:bg-white/5"
            onMouseEnter={(e) => onCharacterEnter(characterId, e.currentTarget.getBoundingClientRect())}
            onMouseLeave={() => onCharacterLeave(characterId)}
          >
            <Avatar name={message.characterName} color={color} size={28} />
            <span className="text-sm font-medium" style={{ color }}>
              {message.characterName}
            </span>
          </button>
        )}
        <span className="rounded-full bg-black/30 px-2 py-0.5 text-xs text-stone-400">
          {meta.icon} {meta.label}
        </span>
        <time className="ml-auto font-mono text-xs text-stone-500">{formatClock(message.timestamp)}</time>
      </header>

      <p
        className={cn(
          'mt-2 text-[15px] leading-relaxed',
          (message.type === 'dialogue' || message.type === 'npc') && 'font-serif text-stone-100',
          message.type === 'action' && 'italic text-stone-300',
          message.type === 'env' && 'text-stone-300',
          message.type === 'scene_change' && 'text-center font-serif text-gold/90',
        )}
      >
        {message.content}
      </p>

      {message.innerThought && characterId !== null && (
        <InnerThoughtToggle thought={message.innerThought} color={color} name={message.characterName} />
      )}
    </motion.article>
  )
}
