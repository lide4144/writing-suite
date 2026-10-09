// 像素舞台：消息流的剧场化渲染。
// 直播 = 演出队列按 dwellMs 逐条推进；时间轴跳转 = seekTarget 直接定位 playhead；
// 跳转后暂停自动演出，点「回到现场」或 seek 到最新一条时恢复跟随。

import { useEffect, useMemo, useState } from 'react'
import type { CharacterInfo, Message } from '../../types'
import { computeSnapshot, dwellMs } from './stageDirector'
import { PixelActor } from './PixelActor'
import { SpeechBubble } from './SpeechBubble'
import { cn } from '../../utils/cn'
import type { SeekTarget } from '../watch/ActivityFeed'

interface PixelStageProps {
  messages: Message[]
  characters: CharacterInfo[]
  ended: boolean
  seekTarget: SeekTarget | null
  onCharacterEnter: (characterId: string, rect: DOMRect) => void
  onCharacterLeave: () => void
}

const LIGHTING_CLASS = {
  day: 'from-[#2b3444] via-[#232a38] to-[#1a1f2b]',
  dusk: 'from-[#3d2f2a] via-[#2b2430] to-[#1a1a26]',
  night: 'from-[#141824] via-[#10131d] to-[#0c0e16]',
} as const

export function PixelStage({ messages, characters, ended, seekTarget, onCharacterEnter, onCharacterLeave }: PixelStageProps) {
  const [playhead, setPlayhead] = useState(() => Math.max(0, messages.length - 1))
  const [paused, setPaused] = useState(false)

  // 时间轴跳转：定位 playhead；跳到非最新条则暂停演出
  useEffect(() => {
    if (!seekTarget) return
    const idx = messages.findIndex((m) => m.id === seekTarget.id)
    if (idx === -1) return
    setPlayhead(idx)
    setPaused(idx < messages.length - 1)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [seekTarget])

  // 演出队列：未暂停且未到最新时，按驻留时长逐条推进
  useEffect(() => {
    if (paused || playhead >= messages.length - 1) return
    const timer = window.setTimeout(() => setPlayhead((p) => p + 1), dwellMs(messages[playhead]))
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paused, playhead, messages.length])

  const snapshot = useMemo(
    () => computeSnapshot(messages, characters, playhead),
    [messages, characters, playhead],
  )

  const currentMessage = messages[playhead] ?? null
  const bubbleActor = snapshot.bubble?.characterId
    ? snapshot.actors.find((a) => a.characterId === snapshot.bubble?.characterId)
    : null
  const thoughtActor = currentMessage?.characterId
    ? snapshot.actors.find((a) => a.characterId === currentMessage.characterId)
    : null
  const colorOf = (characterId: string | null | undefined) =>
    characters.find((c) => c.id === characterId)?.color

  const resumeLive = () => {
    setPlayhead(Math.max(0, messages.length - 1))
    setPaused(false)
  }

  // 落幕幕布仅在「已落幕且未回看历史」时合拢；拖动时间轴回看（paused）时分开
  const curtainClosed = ended && !paused

  return (
    <div className={cn('relative h-full overflow-hidden bg-gradient-to-b', LIGHTING_CLASS[snapshot.lighting])}>
      {/* 顶部舞台灯 */}
      <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex justify-around">
        {characters.map((c) => (
          <div
            key={c.id}
            className="h-40 w-32 opacity-25 transition-colors duration-700"
            style={{ background: `linear-gradient(to bottom, ${c.color}66, transparent)` }}
          />
        ))}
      </div>

      {/* 雨 */}
      {snapshot.weather !== 'clear' && (
        <div className={cn('pointer-events-none absolute inset-0 z-10', snapshot.weather === 'heavy-rain' ? 'pixel-rain-heavy' : 'pixel-rain')} />
      )}

      {/* 章节卡：常驻显示当前章节 */}
      {snapshot.chapter && (
        <div className="absolute left-1/2 top-6 z-20 -translate-x-1/2 rounded-full border border-gold/30 bg-stage-950/70 px-4 py-1 text-xs tracking-[0.4em] text-gold">
          {snapshot.chapter}
        </div>
      )}

      {/* 幕布脉冲（scene_change） */}
      {snapshot.sceneChangeId && (
        <div key={snapshot.sceneChangeId} className="pointer-events-none absolute inset-0 z-30">
          <div className="curtain-pulse-left absolute inset-y-0 left-0 w-[38vw] bg-gradient-to-r from-[#5a1f24] to-[#3d1519]" />
          <div className="curtain-pulse-right absolute inset-y-0 right-0 w-[38vw] bg-gradient-to-l from-[#5a1f24] to-[#3d1519]" />
        </div>
      )}

      {/* 地板 */}
      <div
        className="absolute inset-x-0 bottom-0 h-[24%] border-t-2 border-[#4a3b28]"
        style={{
          background:
            'repeating-linear-gradient(to bottom, #3d2f20 0 6px, #35281b 6px 12px), linear-gradient(to bottom, #3d2f20, #2a2016)',
        }}
      />
      {/* 两侧常驻侧幕 */}
      <div className="pointer-events-none absolute inset-y-0 left-0 z-20 w-6 bg-gradient-to-r from-[#5a1f24] to-transparent" />
      <div className="pointer-events-none absolute inset-y-0 right-0 z-20 w-6 bg-gradient-to-l from-[#5a1f24] to-transparent" />

      {/* 演员 */}
      {snapshot.actors.map((a) => (
        <div
          key={a.characterId}
          className="absolute bottom-[18%] z-10 transition-[left] duration-700 ease-in-out"
          style={{ left: `${a.x}%`, transform: 'translateX(-50%)' }}
        >
          {/* 气泡：对话泡挂说话者头顶（w-max 避免被 48px 演员容器压窄） */}
          {bubbleActor?.characterId === a.characterId && snapshot.bubble && (
            <div className="absolute -top-16 left-1/2 z-20 w-max -translate-x-1/2">
              <SpeechBubble text={snapshot.bubble.text} kind="dialogue" color={colorOf(a.characterId)} />
            </div>
          )}
          {/* 思想泡：略高、错开 */}
          {thoughtActor?.characterId === a.characterId && snapshot.thought && (
            <div className={cn('absolute left-1/2 z-20 w-max -translate-x-1/2', bubbleActor?.characterId === a.characterId ? '-top-32' : '-top-16')}>
              <SpeechBubble text={snapshot.thought} kind="thought" />
            </div>
          )}
          <PixelActor
            characterId={a.characterId}
            name={characters.find((c) => c.id === a.characterId)?.name ?? ''}
            pose={a.pose}
            facing={a.facing}
            emote={a.emote}
            onEnter={onCharacterEnter}
            onLeave={onCharacterLeave}
          />
          {/* 脚下名签 */}
          <div className="mt-1 text-center text-[10px] tracking-widest" style={{ color: colorOf(a.characterId) }}>
            {characters.find((c) => c.id === a.characterId)?.name}
          </div>
        </div>
      ))}

      {/* GM 气泡（npc 类型且 characterId 为 null 时）：舞台顶部居中 */}
      {snapshot.bubble && snapshot.bubble.characterId === null && (
        <div className="absolute left-1/2 top-14 z-20 -translate-x-1/2">
          <SpeechBubble text={snapshot.bubble.text} kind="dialogue" />
        </div>
      )}

      {/* 字幕条 */}
      {snapshot.subtitle && (
        <div className="absolute inset-x-0 bottom-2 z-20 flex justify-center">
          <p className="max-w-2xl truncate rounded bg-stage-950/80 px-4 py-1.5 font-serif text-sm italic text-stone-300">
            {snapshot.subtitle}
          </p>
        </div>
      )}

      {/* 空场景 */}
      {messages.length === 0 && (
        <div className="absolute inset-0 z-20 flex items-center justify-center">
          <p className="font-serif text-lg text-stone-500">舞台空无一人，等待开场…</p>
        </div>
      )}

      {/* 暂停演出时的回到现场按钮 */}
      {paused && (
        <button
          type="button"
          onClick={resumeLive}
          className="absolute bottom-10 right-4 z-30 rounded-full border border-gold/40 bg-stage-950/85 px-4 py-1.5 text-xs text-gold shadow-lg transition-colors hover:bg-stage-800"
        >
          ▶ 回到现场
        </button>
      )}

      {/* 落幕：幕布合拢 + 金字；用户拖动时间轴回看历史（paused）时幕布分开，舞台可回放 */}
      <div
        className={cn(
          'pointer-events-none absolute inset-y-0 left-0 z-40 w-1/2 bg-gradient-to-r from-[#5a1f24] via-[#4a1a1e] to-[#3d1519] transition-transform duration-[2000ms] ease-in-out',
          curtainClosed ? 'translate-x-0' : '-translate-x-full',
        )}
      />
      <div
        className={cn(
          'pointer-events-none absolute inset-y-0 right-0 z-40 w-1/2 bg-gradient-to-l from-[#5a1f24] via-[#4a1a1e] to-[#3d1519] transition-transform duration-[2000ms] ease-in-out',
          curtainClosed ? 'translate-x-0' : 'translate-x-full',
        )}
      />
      {curtainClosed && (
        <div className="pointer-events-none absolute inset-0 z-50 flex items-center justify-center">
          <span className="font-serif text-4xl tracking-[1em] text-gold drop-shadow-[0_0_18px_rgba(201,168,106,0.5)]">
            落幕
          </span>
        </div>
      )}
    </div>
  )
}
