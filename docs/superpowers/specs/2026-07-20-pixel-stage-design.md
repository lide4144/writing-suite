# 像素舞台（Pixel Stage）设计文档

> 基于 FRONTEND_SPEC.md 的观众席，新增「像素舞台」视图：角色以像素小人在舞台上演出消息流。
> 版本：v0.1 | 日期：2026-07-20 | 状态：设计已确认，待实现

---

## 1. 定位与入口

- 观众席中栏顶部加视图切换：`📜 活动流 / 🎪 像素舞台`，是 WatchPage 内的视图状态，**不切路由**。
- 完整复用 `useSceneWatch` 的数据（消息流、角色表、直播推送、落幕状态、里程碑）。
- 底部时间轴、浮动仪表盘、演员表在舞台视图下照常可用。
- 后续迭代（不在本期范围）：像素工作室页面（俯视监控台）。

## 2. 舞台导演（stageDirector.ts，纯逻辑状态机）

输入：消息列表 + 角色表 + 当前时刻。输出：舞台快照 `StageSnapshot`。

```typescript
interface StageSnapshot {
  backdrop: {
    weather: 'clear' | 'rain' | 'heavy-rain'
    lighting: 'day' | 'dusk' | 'night'
    sceneLabel: string
  }
  actors: ActorPlacement[] // characterId、x 位置(0-100)、facing、pose: idle|talk|walk|emote、visible
  currentSpeaker: string | null
  bubble: { characterId: string | null; text: string; kind: 'dialogue' | 'action' | 'env' | 'thought' } | null
  chapter: string | null
}
```

消息类型 → 舞台指令映射：

| 消息类型 | 舞台行为 |
|----------|----------|
| `env` | 改布景氛围（"雨/灯/夜"等关键词驱动天气与灯光渐变），叙述上字幕条 |
| `dialogue` | 说话者走到舞台前区、面向观众，头顶冒对话气泡 |
| `action` | 角色走位/转身（walk pose），叙述上字幕条 |
| `scene_change` | 幕布转场（暗场 + 章节标题卡） |
| `innerThought` | 半透明思想泡泡（呼应 spec §8.2 内心独白分层展示，全知读者可见） |

两种驱动模式：

- **直播**：新消息进演出队列，每条驻留时长随文本长度变化（基础 ~1.2s + 按字数递增），依次推进。
- **回放/跳转**：给定时刻 T，从消息历史计算 T 时刻的舞台快照（谁在台上、最近 env 的天气灯光、最近说话者），直接渲染该快照。这是状态机相对"消息即动画"的核心优势，时间轴拖拽与 ▶ 回放天然兼容。

## 3. 像素小人（PixelActor.tsx + pixelActors.ts）

- 16×24 像素网格，CSS `box-shadow` 单层绘制（经典 pixel-art 技法），零图片资源。
- 参数化形象：发色、肤色、衣服主色（= 角色主题色）、标志性配饰：
  - 林晚：笔记本/笔
  - 沈聿：马克杯
  - 顾遥：连帽衫
  - 苏黎：眼镜
- 纯 CSS 动画：
  - `idle`：呼吸起伏（translateY 1px 循环）
  - `talk`：身体轻微弹跳 + 气泡出现
  - `walk`：双腿两帧交替 + translateX 过渡
  - `emote`：头顶情绪符号（💢💧❗）
  - 朝向：`scaleX(-1)` 翻转
- GM 不上台，以舞台顶部横幅/字幕表现。

## 4. 舞台场景（PixelStage.tsx）

- 构图：深色剧场背景 + 像素木纹地板 + 两侧幕布 + 顶部舞台灯。
- 布景由 backdrop 驱动：雨（CSS 粒子/重复背景动画，clear/rain/heavy-rain 三档密度）、灯光冷暖渐变（day/dusk/night）。
- 舞台底部「字幕条」显示 env/action 叙述（戏剧字幕机）。
- 气泡（SpeechBubble.tsx）：像素阶梯边框；对话气泡用角色色边框；思想泡半透明、云形。
- `scene_change`：两侧幕布 CSS 动画合拢再拉开 + 章节标题卡。
- 落幕（ended）：幕布合拢 + 金字「落幕」。

## 5. 与现有交互整合

- 悬停/点击小人 → 复用 WatchPage 现有浮动仪表盘回调（`handleCharacterEnter` / `pinCharacter`）。
- 时间轴拖拽/回放 → 设置"当前时刻"，舞台渲染该时刻快照。
- 直播新消息 → 追加到演出队列。
- 用户拖拽时间轴时暂停演出队列，「回到最新」时恢复直播跟随。

## 6. 文件划分

全部新增于 `web/src/components/stage/`，不改动现有组件内部：

| 文件 | 职责 |
|------|------|
| `stageDirector.ts` | 导演状态机（纯函数，便于日后单测） |
| `PixelStage.tsx` | 舞台容器：布景、灯光、幕布、字幕条 |
| `PixelActor.tsx` | 像素小人渲染与动画 |
| `pixelActors.ts` | 4 个角色的形象参数表 |
| `SpeechBubble.tsx` | 对话气泡 / 思想泡 |

既有文件改动：

- `WatchPage.tsx`：加视图切换 state + 顶部切换按钮 + 舞台视图分支（替换 ActivityFeed 的位置）。
- `index.css`：像素动画 keyframes（呼吸、走路、雨、幕布）。

测试策略：项目当前无测试框架，本期不引入；stageDirector 保持纯函数设计，以浏览器实测验证。

## 7. 异常处理

| 情况 | 处理 |
|------|------|
| 空场景（无消息） | 空舞台 + 「等待开场…」字幕 |
| 未知 characterId（无形象参数） | 默认灰色小人 |
| 拖拽时间轴与直播推送竞争 | 拖拽/回放期间暂停演出队列，回到最新时恢复 |
| 场景已落幕 | 幕布合拢 + 「落幕」金字，舞台只读 |

## 8. 明确不做（YAGNI）

- 像素工作室页面（后续迭代，另立设计）。
- Canvas 渲染、sprite 图片素材、AI 生成形象。
- 小人点击后的新交互（沿用现有仪表盘）。
- 测试框架引入。
