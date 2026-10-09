// 舞台导演（纯函数，无 React 依赖）：把消息流翻译成舞台快照。
// 两种用法：直播 = 逐条推进 playhead；回放/跳转 = 给定 playhead 直接算快照。

import type { CharacterInfo, Message } from '../../types'
import type { ActorPose } from './PixelActor'

export type Weather = 'clear' | 'rain' | 'heavy-rain'
export type Lighting = 'day' | 'dusk' | 'night'

export interface ActorPlacement {
  characterId: string
  x: number // 舞台横向位置 0-100（百分比）
  facing: 'left' | 'right'
  pose: ActorPose
  emote: string | null
}

export interface StageBubble {
  characterId: string | null // null = GM
  text: string
  kind: 'dialogue' | 'thought'
}

export interface StageSnapshot {
  weather: Weather
  lighting: Lighting
  actors: ActorPlacement[]
  /** 当前对话气泡（messages[playhead] 为 dialogue 时） */
  bubble: StageBubble | null
  /** 当前消息的内心独白 → 思想泡 */
  thought: string | null
  /** env/action/npc 的叙述字幕 */
  subtitle: string | null
  /** 最近一个 scene_change 的消息 id（驱动幕布脉冲），无则 null */
  sceneChangeId: string | null
  chapter: string | null
}

// ---- 布景关键词解析（基于 env 叙述文本） ----

export function weatherOf(text: string, prev: Weather): Weather {
  if (/雨刚停|雨停了|雨停|放晴|转晴/.test(text)) return 'clear'
  if (/暴雨|大雨|倾盆|密成一片/.test(text)) return 'heavy-rain'
  if (/雨点|雨声|雨幕|下雨|雨水|第一滴雨/.test(text)) return 'rain'
  return prev
}

export function lightingOf(text: string, prev: Lighting): Lighting {
  if (/深夜|夜里|夜晚|凌晨|夜色/.test(text)) return 'night'
  if (/黄昏|傍晚|斜阳|夕阳|暗下来|灯.*亮|亮起/.test(text)) return 'dusk'
  if (/清晨|早晨|正午|午后|阳光/.test(text)) return 'day'
  return prev
}

/** 演出驻留时长：随文本长度变化，1.2s ~ 4s */
export function dwellMs(message: Message): number {
  return Math.min(1200 + message.content.length * 45, 4000)
}

/** 演员初始站位：在 20%~80% 区间均分 */
function slotX(index: number, total: number): number {
  if (total <= 1) return 50
  return 20 + (index * 60) / (total - 1)
}

/**
 * 计算 playhead 时刻的舞台快照。
 * 从头扫描 messages[0..playhead]，提炼布景状态；playhead 条决定气泡/字幕/姿态。
 */
export function computeSnapshot(
  messages: Message[],
  characters: CharacterInfo[],
  playhead: number,
): StageSnapshot {
  const sorted = messages // 调用方保证已按时间升序
  let weather: Weather = 'clear'
  let lighting: Lighting = 'day'
  let sceneChangeId: string | null = null
  let chapter: string | null = null

  const end = Math.min(playhead, sorted.length - 1)
  for (let i = 0; i <= end; i++) {
    const m = sorted[i]
    if (m.type === 'env' || m.type === 'scene_change') {
      weather = weatherOf(m.content, weather)
      lighting = lightingOf(m.content, lighting)
    }
    if (m.type === 'scene_change') sceneChangeId = m.id
    if (m.chapter) chapter = m.chapter
  }

  const current = sorted[end] ?? null
  const center = 50

  const actors: ActorPlacement[] = characters.map((c, i) => {
    const x = slotX(i, characters.length)
    let pose: ActorPose = 'idle'
    let emote: string | null = null
    if (current && current.characterId === c.id) {
      if (current.type === 'dialogue') pose = 'talk'
      else if (current.type === 'action') pose = 'walk'
      if (current.innerThought && current.importance >= 6) {
        pose = 'emote'
        emote = current.importance >= 8 ? '❗' : '💧'
      }
    }
    return { characterId: c.id, x, facing: x < center ? 'right' : 'left', pose, emote }
  })

  let bubble: StageBubble | null = null
  let thought: string | null = null
  let subtitle: string | null = null
  if (current) {
    if (current.type === 'dialogue' || current.type === 'npc') {
      bubble = { characterId: current.characterId, text: current.content, kind: 'dialogue' }
    } else if (current.type === 'env' || current.type === 'action' || current.type === 'scene_change') {
      subtitle = current.content
    }
    if (current.innerThought) thought = current.innerThought
  }

  return { weather, lighting, actors, bubble, thought, subtitle, sceneChangeId, chapter }
}
