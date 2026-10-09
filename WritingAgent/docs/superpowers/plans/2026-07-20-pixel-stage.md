# 像素舞台（Pixel Stage）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在观众席内新增「像素舞台」视图：角色以参数化像素小人在舞台上演出消息流，直播/回放/时间轴跳转均可驱动。

**Architecture:** 舞台导演状态机（`stageDirector.ts` 纯函数）把消息流翻译成舞台快照；渲染层（`PixelStage`/`PixelActor`/`SpeechBubble`）只负责演出。CSS box-shadow 绘制 16×24 像素小人，零图片资源。观众席内视图切换，不切路由，完整复用 `useSceneWatch`。

**Tech Stack:** React 18 + TypeScript + Tailwind CSS 3 + framer-motion（已装）；无新增依赖；项目无测试框架，验证方式为 `npx tsc -b` + 浏览器实测。

**Spec:** `docs/superpowers/specs/2026-07-20-pixel-stage-design.md`

**既有事实（实现时直接引用，不要重新探查）：**
- 角色 id 与主题色（`web/src/mock/data.ts:41-44`）：`char-lin-wan` 林晚 `#e8927c`、`char-shen-yu` 沈聿 `#6a9bd8`、`char-gu-yao` 顾遥 `#8fbf6a`、`char-su-li` 苏黎 `#c987d6`；GM 色 `GM_COLOR = '#8a8a96'`。
- `Message.type`：`'env' | 'npc' | 'action' | 'dialogue' | 'scene_change'`；`innerThought: string | null`；`chapter: string | null`；`importance: number`。
- `WatchPage.tsx` 已有：`seekTarget: SeekTarget | null`（`{ id, nonce }`）、`seek(id)`、`handleCharacterEnter(characterId, rect)`、`scheduleHoverClose()`、以及 ActivityFeed 的渲染分支（约 166-180 行）。
- CSS 自定义动画集中在 `web/src/index.css` 末尾（参照现有 `@keyframes breathe` 的写法）。
- Tailwind 自定义色：`stage-950/900/800/700/600`（深石板系）、`gold`（`#c9a86a` 系），见 `web/tailwind.config.js`。

---

## 文件结构

| 文件 | 职责 | 新建/修改 |
|------|------|-----------|
| `web/src/components/stage/sprites.ts` | 16×24 像素图（基础帧/走路帧/发型变体行）、调色板类型、`buildShadow` 工具 | 新建 |
| `web/src/components/stage/pixelActors.ts` | 4 个角色的形象参数表 `PIXEL_LOOKS` + `DEFAULT_LOOK` | 新建 |
| `web/src/components/stage/PixelActor.tsx` | 单个像素小人渲染（box-shadow）与 idle/talk/walk/emote 动画、配饰 | 新建 |
| `web/src/components/stage/stageDirector.ts` | 纯函数：关键词布景解析、`computeSnapshot`、`dwellMs` | 新建 |
| `web/src/components/stage/SpeechBubble.tsx` | 像素阶梯边框气泡（对话/思想两种） | 新建 |
| `web/src/components/stage/PixelStage.tsx` | 舞台容器：布景、雨、灯光、幕布、字幕条、落幕；演出队列 hook | 新建 |
| `web/src/index.css` | 像素动画 keyframes（idle/talk/walk/rain/curtain/bubble） | 修改（末尾追加） |
| `web/src/pages/WatchPage.tsx` | 视图切换 state + 切换按钮 + 舞台视图分支 | 修改 |

---

## Task 1: 像素图数据（sprites.ts + pixelActors.ts）

**Files:**
- Create: `web/src/components/stage/sprites.ts`
- Create: `web/src/components/stage/pixelActors.ts`

- [ ] **Step 1: 创建 `web/src/components/stage/sprites.ts`**

16 列 × 24 行像素图。字符含义：`h`=头发/兜帽，`s`=皮肤，`e`=眼睛，`m`=嘴，`t`=上衣，`p`=裤子，`o`=鞋，`.`=透明。每行严格 16 字符。

```typescript
// 像素小人图数据：16 列 × 24 行，字符映射到调色板（见 PixelActor.tsx）。
// h=头发/兜帽 s=皮肤 e=眼睛 m=嘴 t=上衣 p=裤子 o=鞋 .=透明

export type SpriteRows = string[]

/** 基础帧（站立） */
export const BASE_SPRITE: SpriteRows = [
  '.....hhhhhh.....',
  '...hhhhhhhhhh...',
  '..hhhhhhhhhhhh..',
  '..hhsssssssshh..',
  '..hhsssssssshh..',
  '..hseesssseesh..',
  '..hsssmmmmsssh..',
  '......ssss......',
  '...tttttttttt...',
  '..tttttttttttt..',
  '.tttttttttttttt.',
  '.tttttttttttttt.',
  '.tssttttttttsst.',
  '.tssttttttttsst.',
  '..tttttttttttt..',
  '..tttttttttttt..',
  '..pppppppppppp..',
  '...ppp....ppp...',
  '...ppp....ppp...',
  '...ppp....ppp...',
  '...ppp....ppp...',
  '...ppp....ppp...',
  '...ppp....ppp...',
  '..oooo....oooo..',
]

/** 走路帧：仅腿部行（17-23）不同，两腿岔开 */
export const WALK_SPRITE: SpriteRows = [
  ...BASE_SPRITE.slice(0, 17),
  '..ppp......ppp..',
  '..ppp......ppp..',
  '..ppp......ppp..',
  '..ppp......ppp..',
  '..ppp......ppp..',
  '..ppp......ppp..',
  '.ooo........ooo.',
]

/** 发型变体：按行号替换基础帧的对应行 */
export const HAIR_VARIANTS = {
  short: {} as Record<number, string>,
  long: {
    4: '.hhsssssssssshh.',
    5: '.hhseesssseeshh.',
    6: '.hhsssmmmmssshh.',
    7: '.hh...ssss...hh.',
    8: '.hh.tttttttt.hh.',
  } as Record<number, string>,
  bun: {
    0: '....hhhhhhhh....',
  } as Record<number, string>,
  hood: {
    2: '.hhhhhhhhhhhhhh.',
    3: '.hhhsssssssshhh.',
    4: '.hhsssssssssshh.',
    5: '.hhseesssseeshh.',
    6: '.hhsssmmmmssshh.',
  } as Record<number, string>,
}

export type HairStyle = keyof typeof HAIR_VARIANTS

/** 应用发型变体，得到完整像素图 */
export function applyHair(base: SpriteRows, style: HairStyle): SpriteRows {
  const patch = HAIR_VARIANTS[style]
  return base.map((row, i) => patch[i] ?? row)
}

export const SPRITE_W = 16
export const SPRITE_H = 24

/**
 * 把像素图编译成 CSS box-shadow 串（经典单元素 pixel-art 技法）。
 * palette: 字符 → 颜色；px: 单像素边长。
 */
export function buildShadow(rows: SpriteRows, palette: Record<string, string>, px: number): string {
  const parts: string[] = []
  rows.forEach((row, y) => {
    for (let x = 0; x < row.length; x++) {
      const color = palette[row[x]]
      if (color) parts.push(`${x * px}px ${y * px}px 0 0 ${color}`)
    }
  })
  return parts.join(',')
}
```

- [ ] **Step 2: 创建 `web/src/components/stage/pixelActors.ts`**

```typescript
// 角色像素形象参数表：发色/肤色/衣服色（=角色主题色）/发型/标志性配饰。
// 未登记的角色用 DEFAULT_LOOK（灰色小人）。

import type { HairStyle } from './sprites'

export type Accessory = 'notebook' | 'mug' | 'glasses' | null

export interface PixelLook {
  hair: string
  skin: string
  top: string
  pants: string
  hairStyle: HairStyle
  accessory: Accessory
}

export const DEFAULT_LOOK: PixelLook = {
  hair: '#4a4a52',
  skin: '#e8c0a0',
  top: '#8a8a96',
  pants: '#3a3f4a',
  hairStyle: 'short',
  accessory: null,
}

export const PIXEL_LOOKS: Record<string, PixelLook> = {
  'char-lin-wan': {
    hair: '#4a3728',
    skin: '#f0c8a8',
    top: '#e8927c',
    pants: '#3a3f4a',
    hairStyle: 'long',
    accessory: 'notebook',
  },
  'char-shen-yu': {
    hair: '#2a2a30',
    skin: '#ecc09c',
    top: '#6a9bd8',
    pants: '#2e3440',
    hairStyle: 'short',
    accessory: 'mug',
  },
  'char-gu-yao': {
    hair: '#4e6b3f', // 兜帽色
    skin: '#f0c8a8',
    top: '#8fbf6a',
    pants: '#3a3f4a',
    hairStyle: 'hood',
    accessory: null,
  },
  'char-su-li': {
    hair: '#3a2a4a',
    skin: '#f0c8a8',
    top: '#c987d6',
    pants: '#2e3440',
    hairStyle: 'bun',
    accessory: 'glasses',
  },
}

export function lookOf(characterId: string): PixelLook {
  return PIXEL_LOOKS[characterId] ?? DEFAULT_LOOK
}
```

- [ ] **Step 3: 类型检查**

Run: `cd web && npx tsc -b`
Expected: 无错误（新文件暂未引用，仅验证语法与类型）。

- [ ] **Step 4: Commit**

```bash
git add web/src/components/stage/sprites.ts web/src/components/stage/pixelActors.ts
git commit -m "feat(stage): 像素小人图数据与角色形象参数表"
```

---

## Task 2: PixelActor 组件 + 像素动画 CSS

**Files:**
- Create: `web/src/components/stage/PixelActor.tsx`
- Modify: `web/src/index.css`（末尾追加）

- [ ] **Step 1: 在 `web/src/index.css` 末尾追加像素动画**

```css
/* ---- 像素舞台 ---- */

/* 待机呼吸 */
@keyframes pixel-idle {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-2px);
  }
}
.pixel-idle {
  animation: pixel-idle 2.4s ease-in-out infinite;
}

/* 说话弹跳 */
@keyframes pixel-talk {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-3px);
  }
}
.pixel-talk {
  animation: pixel-talk 0.5s ease-in-out infinite;
}

/* 走路：两帧交替（steps(1) 硬切） */
@keyframes pixel-walk-swap {
  0%,
  49% {
    opacity: 1;
  }
  50%,
  100% {
    opacity: 0;
  }
}
.pixel-walk-frame {
  animation: pixel-walk-swap 0.36s steps(1) infinite;
}

/* 雨：斜线纹理下落 */
@keyframes pixel-rain {
  from {
    background-position: 0 0;
  }
  to {
    background-position: -40px 120px;
  }
}
.pixel-rain {
  background-image: repeating-linear-gradient(
    105deg,
    transparent 0 6px,
    rgba(150, 180, 220, 0.18) 6px 7px,
    transparent 7px 14px
  );
  background-size: 80px 120px;
  animation: pixel-rain 0.7s linear infinite;
}
.pixel-rain-heavy {
  background-image: repeating-linear-gradient(
      105deg,
      transparent 0 4px,
      rgba(150, 180, 220, 0.22) 4px 5px,
      transparent 5px 10px
    ),
    repeating-linear-gradient(100deg, transparent 0 8px, rgba(150, 180, 220, 0.14) 8px 9px, transparent 9px 18px);
  background-size:
    60px 100px,
    90px 140px;
  animation: pixel-rain 0.45s linear infinite;
}

/* 气泡出现 */
@keyframes pixel-bubble-pop {
  from {
    opacity: 0;
    transform: translateY(6px) scale(0.92);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}
.pixel-bubble-pop {
  animation: pixel-bubble-pop 0.18s ease-out;
}

/* scene_change 幕布脉冲：两侧红色幕布快速合拢再拉开（每个 scene_change 触发一次） */
@keyframes curtain-pulse-left {
  0%,
  100% {
    transform: translateX(0);
  }
  40%,
  60% {
    transform: translateX(38vw);
  }
}
@keyframes curtain-pulse-right {
  0%,
  100% {
    transform: translateX(0);
  }
  40%,
  60% {
    transform: translateX(-38vw);
  }
}
.curtain-pulse-left {
  animation: curtain-pulse-left 1.6s ease-in-out;
}
.curtain-pulse-right {
  animation: curtain-pulse-right 1.6s ease-in-out;
}

/* 落幕：幕布常驻合拢态由组件内联 transition 控制，不用 keyframes */
```

- [ ] **Step 2: 创建 `web/src/components/stage/PixelActor.tsx`**

```tsx
// 像素小人：CSS box-shadow 单元素绘制 16×24 像素图，纯 CSS 动画。
// pose: idle（呼吸）/ talk（弹跳）/ walk（两帧交替 + 位移由父级 transition 完成）。
// facing 用内层 scaleX(-1) 翻转；呼吸/弹跳动画放在外层避免 transform 冲突。

import { useMemo } from 'react'
import { applyHair, BASE_SPRITE, buildShadow, SPRITE_H, SPRITE_W, WALK_SPRITE } from './sprites'
import { lookOf } from './pixelActors'
import { cn } from '../../utils/cn'

export type ActorPose = 'idle' | 'talk' | 'walk' | 'emote'

const PX = 3 // 单像素边长（px），整体 48×72

interface PixelActorProps {
  characterId: string
  name: string
  pose: ActorPose
  facing: 'left' | 'right'
  emote: string | null
  onEnter?: (characterId: string, rect: DOMRect) => void
  onLeave?: () => void
}

function paletteOf(look: ReturnType<typeof lookOf>): Record<string, string> {
  return {
    h: look.hair,
    s: look.skin,
    e: '#26262e',
    m: '#b46a5a',
    t: look.top,
    p: look.pants,
    o: '#26262e',
  }
}

export function PixelActor({ characterId, name, pose, facing, emote, onEnter, onLeave }: PixelActorProps) {
  const look = lookOf(characterId)

  // 每个形象编译一次 box-shadow（含发型变体）
  const { idleShadow, walkShadow } = useMemo(() => {
    const palette = paletteOf(look)
    const idle = applyHair(BASE_SPRITE, look.hairStyle)
    const walk = applyHair(WALK_SPRITE, look.hairStyle)
    return {
      idleShadow: buildShadow(idle, palette, PX),
      walkShadow: buildShadow(walk, palette, PX),
    }
  }, [look])

  const walking = pose === 'walk'

  return (
    <div
      role="img"
      aria-label={name}
      className={cn('relative cursor-pointer', pose === 'idle' && 'pixel-idle', (pose === 'talk' || pose === 'emote') && 'pixel-talk')}
      style={{ width: SPRITE_W * PX, height: SPRITE_H * PX, imageRendering: 'pixelated' }}
      onMouseEnter={(e) => onEnter?.(characterId, e.currentTarget.getBoundingClientRect())}
      onMouseLeave={onLeave}
    >
      <div style={{ transform: facing === 'left' ? 'scaleX(-1)' : undefined }}>
        {/* 站立帧 */}
        <div style={{ width: PX, height: PX, boxShadow: idleShadow }} />
        {/* 走路帧：叠加，steps(1) 交替显隐 */}
        {walking && (
          <div className="pixel-walk-frame absolute left-0 top-0" style={{ width: PX, height: PX, boxShadow: walkShadow }} />
        )}
        {/* 配饰 */}
        {look.accessory === 'notebook' && (
          <div
            className="absolute"
            style={{ left: 12 * PX, top: 11 * PX, width: 4 * PX, height: 5 * PX, backgroundColor: '#7a5a3a', boxShadow: `inset ${PX}px 0 0 #d8cbb0` }}
          />
        )}
        {look.accessory === 'mug' && (
          <div
            className="absolute"
            style={{ left: 0, top: 12 * PX, width: 3 * PX, height: 3 * PX, backgroundColor: '#d8d4cc', boxShadow: `${3 * PX}px ${PX}px 0 -1px #d8d4cc` }}
          />
        )}
        {look.accessory === 'glasses' && (
          <>
            <div className="absolute border border-[#26262e]" style={{ left: 4 * PX, top: 5 * PX, width: 3 * PX, height: 2 * PX }} />
            <div className="absolute border border-[#26262e]" style={{ left: 10 * PX, top: 5 * PX, width: 3 * PX, height: 2 * PX }} />
            <div className="absolute bg-[#26262e]" style={{ left: 7 * PX, top: 5 * PX + 1, width: 3 * PX, height: 1 }} />
          </>
        )}
      </div>
      {/* 情绪符号 */}
      {emote && (
        <span className="pixel-bubble-pop absolute -top-4 left-1/2 -translate-x-1/2 text-xs leading-none">{emote}</span>
      )}
    </div>
  )
}
```

- [ ] **Step 3: 类型检查**

Run: `cd web && npx tsc -b`
Expected: 无错误。

- [ ] **Step 4: Commit**

```bash
git add web/src/components/stage/PixelActor.tsx web/src/index.css
git commit -m "feat(stage): PixelActor 像素小人组件与动画"
```

---

## Task 3: 舞台导演（stageDirector.ts）

**Files:**
- Create: `web/src/components/stage/stageDirector.ts`

- [ ] **Step 1: 创建 `web/src/components/stage/stageDirector.ts`**

```typescript
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
```

- [ ] **Step 2: 类型检查 + 快速逻辑冒烟（Node 直接跑编译产物不便，用 tsx 之外的方式）**

Run: `cd web && npx tsc -b`
Expected: 无错误。

- [ ] **Step 3: Commit**

```bash
git add web/src/components/stage/stageDirector.ts
git commit -m "feat(stage): 舞台导演状态机（快照计算与布景解析）"
```

---

## Task 4: SpeechBubble 气泡组件

**Files:**
- Create: `web/src/components/stage/SpeechBubble.tsx`

- [ ] **Step 1: 创建 `web/src/components/stage/SpeechBubble.tsx`**

像素阶梯边框：无圆角实边框 + 两个错位小方块拼成阶梯尾巴。`dialogue` 用角色色边框；`thought` 半透明虚线边框云形（用 rounded-full + 半透明背景区别）。

```tsx
// 像素风气泡：阶梯边框 + 错位方块尾巴。
// dialogue：深色底 + 角色色边框；thought：半透明虚线框（思想泡，全知读者专属）。

import { cn } from '../../utils/cn'

interface SpeechBubbleProps {
  text: string
  kind: 'dialogue' | 'thought'
  color?: string // 角色主题色（dialogue 时传入）
}

export function SpeechBubble({ text, kind, color }: SpeechBubbleProps) {
  if (kind === 'thought') {
    return (
      <div className="pixel-bubble-pop pointer-events-none relative max-w-44 rounded-xl border border-dashed border-stone-400/60 bg-stage-950/70 px-2.5 py-1.5 text-[11px] italic leading-snug text-stone-300">
        💭 {text}
        <span className="absolute -bottom-1.5 left-4 h-1.5 w-1.5 rounded-full bg-stone-400/60" />
        <span className="absolute -bottom-3 left-6 h-1 w-1 rounded-full bg-stone-400/40" />
      </div>
    )
  }
  return (
    <div
      className="pixel-bubble-pop pointer-events-none relative max-w-52 border-2 bg-stage-950/90 px-2.5 py-1.5 text-xs leading-snug text-stone-100"
      style={{ borderColor: color ?? '#8a8a96' }}
    >
      {text}
      {/* 阶梯尾巴 */}
      <span className="absolute -bottom-2 left-3 h-2 w-2" style={{ backgroundColor: color ?? '#8a8a96' }} />
      <span className="absolute -bottom-3.5 left-5 h-1.5 w-1.5" style={{ backgroundColor: color ?? '#8a8a96' }} />
    </div>
  )
}
```

- [ ] **Step 2: 类型检查**

Run: `cd web && npx tsc -b`
Expected: 无错误。

- [ ] **Step 3: Commit**

```bash
git add web/src/components/stage/SpeechBubble.tsx
git commit -m "feat(stage): 像素气泡组件"
```

---

## Task 5: PixelStage 舞台容器（含演出队列）

**Files:**
- Create: `web/src/components/stage/PixelStage.tsx`

- [ ] **Step 1: 创建 `web/src/components/stage/PixelStage.tsx`**

```tsx
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
    setPlayhead(messages.length - 1)
    setPaused(false)
  }

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

      {/* 章节卡：scene_change 时短暂显示 */}
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
          {/* 气泡：对话泡挂说话者头顶 */}
          {bubbleActor?.characterId === a.characterId && snapshot.bubble && (
            <div className="absolute -top-16 left-1/2 z-20 -translate-x-1/2">
              <SpeechBubble text={snapshot.bubble.text} kind="dialogue" color={colorOf(a.characterId)} />
            </div>
          )}
          {/* 思想泡：略高、错开 */}
          {thoughtActor?.characterId === a.characterId && snapshot.thought && (
            <div className={cn('absolute left-1/2 z-20 -translate-x-1/2', bubbleActor?.characterId === a.characterId ? '-top-32' : '-top-16')}>
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

      {/* 落幕：幕布合拢 + 金字 */}
      <div
        className={cn(
          'pointer-events-none absolute inset-y-0 left-0 z-40 w-1/2 bg-gradient-to-r from-[#5a1f24] via-[#4a1a1e] to-[#3d1519] transition-transform duration-[2000ms] ease-in-out',
          ended ? 'translate-x-0' : '-translate-x-full',
        )}
      />
      <div
        className={cn(
          'pointer-events-none absolute inset-y-0 right-0 z-40 w-1/2 bg-gradient-to-l from-[#5a1f24] via-[#4a1a1e] to-[#3d1519] transition-transform duration-[2000ms] ease-in-out',
          ended ? 'translate-x-0' : 'translate-x-full',
        )}
      />
      {ended && (
        <div className="absolute inset-0 z-50 flex items-center justify-center">
          <span className="font-serif text-4xl tracking-[1em] text-gold drop-shadow-[0_0_18px_rgba(201,168,106,0.5)]">
            落幕
          </span>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: 类型检查**

Run: `cd web && npx tsc -b`
Expected: 无错误。

- [ ] **Step 3: Commit**

```bash
git add web/src/components/stage/PixelStage.tsx
git commit -m "feat(stage): 像素舞台容器与演出队列"
```

---

## Task 6: WatchPage 集成（视图切换）

**Files:**
- Modify: `web/src/pages/WatchPage.tsx`

- [ ] **Step 1: 加视图 state 与 import**

文件顶部 import 区追加：

```typescript
import { PixelStage } from '../components/stage/PixelStage'
```

组件内（`const [seekTarget, setSeekTarget] = useState<SeekTarget | null>(null)` 附近）加：

```typescript
// —— 中栏视图：活动流 / 像素舞台 ——
const [view, setView] = useState<'feed' | 'stage'>('feed')
```

- [ ] **Step 2: 替换中栏渲染分支**

把现有（约 166-180 行）：

```tsx
<motion.div
  className="h-full"
  initial={{ opacity: 0 }}
  animate={{ opacity: prologueDone ? 1 : 0 }}
  transition={{ duration: 0.6 }}
>
  <ActivityFeed
    messages={messages}
    characters={characters}
    seekTarget={seekTarget}
    onCharacterEnter={handleCharacterEnter}
    onCharacterLeave={scheduleHoverClose}
  />
</motion.div>
```

改为：

```tsx
<motion.div
  className="h-full"
  initial={{ opacity: 0 }}
  animate={{ opacity: prologueDone ? 1 : 0 }}
  transition={{ duration: 0.6 }}
>
  {view === 'feed' ? (
    <ActivityFeed
      messages={messages}
      characters={characters}
      seekTarget={seekTarget}
      onCharacterEnter={handleCharacterEnter}
      onCharacterLeave={scheduleHoverClose}
    />
  ) : (
    <PixelStage
      messages={messages}
      characters={characters}
      ended={ended}
      seekTarget={seekTarget}
      onCharacterEnter={handleCharacterEnter}
      onCharacterLeave={scheduleHoverClose}
    />
  )}
</motion.div>
```

- [ ] **Step 3: 加视图切换按钮**

在「历史标签」`AnimatePresence` 块之后（同一相对容器内）加浮动切换按钮：

```tsx
{/* 视图切换：活动流 / 像素舞台 */}
{prologueDone && (
  <div className="absolute left-4 top-3 z-20 flex overflow-hidden rounded-full border border-stage-600 bg-stage-900/95 text-xs shadow-lg backdrop-blur">
    <button
      type="button"
      onClick={() => setView('feed')}
      className={cn('px-3 py-1.5 transition-colors', view === 'feed' ? 'bg-gold/20 text-gold' : 'text-stone-400 hover:text-stone-200')}
    >
      📜 活动流
    </button>
    <button
      type="button"
      onClick={() => setView('stage')}
      className={cn('px-3 py-1.5 transition-colors', view === 'stage' ? 'bg-gold/20 text-gold' : 'text-stone-400 hover:text-stone-200')}
    >
      🎪 像素舞台
    </button>
  </div>
)}
```

`cn` 已在 WatchPage import 中则无需新增；若没有则加 `import { cn } from '../utils/cn'`。（实现时先检查文件头部。）

- [ ] **Step 4: 类型检查 + 生产构建**

Run: `cd web && npx tsc -b && npm run build`
Expected: 无错误，`✓ built` 完成。

- [ ] **Step 5: Commit**

```bash
git add web/src/pages/WatchPage.tsx
git commit -m "feat(watch): 观众席集成像素舞台视图切换"
```

---

## Task 7: 浏览器验证（人工检查清单）

**Files:** 无改动，纯验证。

- [ ] **Step 1: 启动 dev server**

Run: `cd web && npm run dev`（后台，端口 5173）

- [ ] **Step 2: 验证像素舞台基础渲染**

打开 `http://localhost:5173/stage/scene-18/watch`，点「🎪 像素舞台」：
- 舞台出现：像素地板、侧幕、顶部灯光、章节卡（当前章节名）
- 林晚（长发/笔记本）、沈聿（短发/马克杯）两个像素小人站在台上，脚下有名签
- 小人待机呼吸动画；切回「📜 活动流」再切回，视图切换正常

- [ ] **Step 3: 验证直播演出**

scene-18 直播脚本播放期间：
- 新对话到达时对应小人变 talk 姿态 + 头顶对话气泡（角色色边框）
- 有 innerThought 的消息出现半透明思想泡
- env 消息上字幕条；含「雨」的 env 触发下雨动画
- 重要消息（importance≥6 且有内心独白）小人头顶出现情绪符号

- [ ] **Step 4: 验证时间轴联动**

- 展开时间轴，点击历史标记点：舞台跳到对应时刻快照（气泡/字幕/布景对应该消息）
- 出现「▶ 回到现场」按钮，点击后恢复直播跟随
- 直播落幕时幕布合拢 + 「落幕」金字出现

- [ ] **Step 5: 验证已落幕场景与 404**

- `/stage/scene-17/watch` 切像素舞台：直接显示落幕幕布
- 悬停小人：浮动仪表盘正常弹出（复用现有交互）

- [ ] **Step 6: Commit（如有修正）**

```bash
git add -A
git commit -m "fix(stage): 浏览器验证修正"
```
