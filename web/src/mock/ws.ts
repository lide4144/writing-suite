// WebSocket 模拟器 —— 对应 spec §9.3 与 §11 Phase 2「定时器驱动消息推送」。
// 以定时器模拟 /ws/scenes/:sceneId 与 /ws/chat/:characterId 两个频道。

import type { CharacterState, Message, WsChatEvent, WsSceneEvent } from '../types'
import { appendSceneMessage, nextId } from './api'
import { CHAT_REPLIES, CHARACTER_STATES, LIVE_SCRIPTS, SCENE_SUMMARIES, SCENES, charStatePatch } from './data'

export interface SocketHandle {
  close(): void
}

/**
 * 直播脚本的落幕安排：脚本消息播完后，场景落幕（scene_ended）并随后生成阶段摘要（summary_ready）。
 * 与 LIVE_SCRIPTS 分离，避免直播脚本本身携带生命周期副作用。
 */
const LIVE_ENDINGS: Record<string, { afterMs: number; summary: string; bullets: string[] }> = {
  'scene-18': {
    afterMs: 12000,
    summary: '雨幕之中，两人达成了暂时的共识，并肩看着窗外。',
    bullets: [
      '林晚和沈聿就项目 deadline 发生了分歧，随后在雨幕中缓和。',
      '沈聿主动提起新项目与顾遥的安排，两人确认不再让他一个人扛。',
      '两人达成暂时的共识，但各自心里仍有保留。',
      '雨声未停，茶水间的灯亮着，场景在并肩的沉默中落幕。',
    ],
  },
}

// ---- 场景频道 ----

export function connectSceneSocket(sceneId: string, onEvent: (event: WsSceneEvent) => void): SocketHandle {
  const timers: ReturnType<typeof setTimeout>[] = []
  const scene = SCENES.find((s) => s.id === sceneId)
  const script = LIVE_SCRIPTS[sceneId]

  if (scene && scene.status === 'running' && script) {
    let elapsed = 0
    script.forEach((step) => {
      elapsed += step.afterMs
      timers.push(
        setTimeout(() => {
          const char = step.characterId ? scene.characters.find((c) => c.id === step.characterId) : null
          const message: Message = {
            id: nextId('msg-live'),
            sceneId,
            timestamp: new Date().toISOString(),
            type: step.type,
            characterId: step.characterId,
            characterName: char ? char.name : 'GM',
            characterAvatar: char ? char.avatar : '',
            content: step.content,
            innerThought: step.innerThought,
            importance: step.importance ?? 3,
            chapter: step.chapter,
          }
          appendSceneMessage(message)
          onEvent({ type: 'message', data: message })

          // 角色行动后推送内部状态更新（§5.5 scene:character_internal）
          if (step.characterId && step.innerThought) {
            const states = CHARACTER_STATES[sceneId] ?? {}
            const patched = charStatePatch(sceneId, step.characterId, step.innerThought)
            onEvent({ type: 'state_change', data: { characterStates: { ...states, ...patched } satisfies Record<string, CharacterState> } })
          }

          if (step.milestone) {
            onEvent({ type: 'milestone', data: step.milestone })
          }
        }, elapsed),
      )
    })

    // —— 落幕链路（§5.5）：脚本播完后 scene_ended，片刻后 summary_ready ——
    const ending = LIVE_ENDINGS[sceneId]
    if (ending) {
      elapsed += ending.afterMs
      timers.push(
        setTimeout(() => {
          scene.status = 'ended'
          scene.endedAt = new Date().toISOString()
          SCENE_SUMMARIES[sceneId] = {
            sceneId,
            generatedAt: scene.endedAt,
            bullets: ending.bullets,
          }
          onEvent({ type: 'scene_ended', data: { summary: ending.summary } })
          timers.push(
            setTimeout(() => {
              onEvent({ type: 'summary_ready', data: { summary: ending.summary } })
            }, 5000),
          )
        }, elapsed),
      )
    }
  }

  return {
    close() {
      timers.forEach(clearTimeout)
    },
  }
}

// ---- Chat 频道 ----

export interface ChatSocketHandle extends SocketHandle {
  send(content: string, fourthWall: boolean): void
}

export function connectChatSocket(characterId: string, onEvent: (event: WsChatEvent) => void): ChatSocketHandle {
  const timers: ReturnType<typeof setTimeout>[] = []
  const replyCursor: Record<string, number> = {}

  return {
    // content 仅用于记录用户输入；mock 回复来自语料池，不 echo 用户内容
    send(_content: string, fourthWall: boolean) {
      const replies = CHAT_REPLIES[characterId]
      if (!replies) return
      const pool = fourthWall ? replies.fourthWall : replies.inWorld
      const key = `${characterId}:${fourthWall}`
      const cursor = replyCursor[key] ?? Math.floor(Math.random() * pool.length)
      replyCursor[key] = cursor + 1
      const full = pool[cursor % pool.length]

      // 流式返回：每 50ms 追加一小段（§7.4 打字指示器 / 流式响应）
      let sent = 0
      const tick = () => {
        sent = Math.min(full.length, sent + 2 + Math.floor(Math.random() * 3))
        const done = sent >= full.length
        onEvent({ type: 'message', data: { content: full.slice(0, sent), done } })
        if (!done) {
          timers.push(setTimeout(tick, 50))
        }
      }
      timers.push(setTimeout(tick, 600)) // 模拟「对方正在输入…」的停顿
    },
    close() {
      timers.forEach(clearTimeout)
    },
  }
}
