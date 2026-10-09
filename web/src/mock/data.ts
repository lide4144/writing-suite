// Mock 数据集 —— 对应 spec §11 Phase 1：场景 ×3、角色 ×4、消息 ×197（场景18 ×100、场景17 ×97）、日记 ×10、记忆 ×20
// 所有时间戳在模块加载时基于当前时间生成，保证「2 分钟前」这类相对时间始终自然。

import type {
  CharacterInfo,
  CharacterState,
  ChatMessage,
  DiaryEntry,
  MemoryItem,
  Message,
  NotificationEvent,
  Scene,
  SceneSummary,
} from '../types'

const NOW = Date.now()
/** n 分钟前的 ISO 时间戳 */
function iso(minutesAgo: number): string {
  return new Date(NOW - minutesAgo * 60000).toISOString()
}

// ---- 角色色板池（§8.1，12-16 种高辨识度颜色，GM 统一灰色） ----
export const CHARACTER_PALETTE = [
  '#e8927c',
  '#6a9bd8',
  '#8fbf6a',
  '#c987d6',
  '#d8b36a',
  '#5ec4b6',
  '#e06c8a',
  '#9a8fe0',
  '#b8d15c',
  '#e0a55c',
  '#6ac8d8',
  '#d87f6a',
]
export const GM_COLOR = '#8a8a96'

// ---- 角色 ×4 ----
export const CHARACTERS: CharacterInfo[] = [
  { id: 'char-lin-wan', name: '林晚', avatar: '', color: '#e8927c' },
  { id: 'char-shen-yu', name: '沈聿', avatar: '', color: '#6a9bd8' },
  { id: 'char-gu-yao', name: '顾遥', avatar: '', color: '#8fbf6a' },
  { id: 'char-su-li', name: '苏黎', avatar: '', color: '#c987d6' },
]

const charById = (id: string): CharacterInfo => CHARACTERS.find((c) => c.id === id)!

// ---- 场景 ×3 ----
export const SCENES: Scene[] = [
  {
    id: 'scene-18',
    title: '午后的茶水间',
    status: 'running',
    description: '雨后的下午，林晚和沈聿在茶水间偶遇。上午会上的 deadline 分歧还没消。',
    characters: [charById('char-lin-wan'), charById('char-shen-yu')],
    totalMessages: 100,
    startedAt: iso(43),
    endedAt: null,
    lastActivityAt: iso(1.2),
    hasUnreadEvents: true,
    setupScript: `# 场景：午后的茶水间

## 基本信息
- 时间：下午两点，雨刚停
- 地点：公司三楼的茶水间
- 角色：林晚（产品经理）、沈聿（后端工程师）

## 初始状态
- 林晚靠在料理台边，手里捏着一支笔，没在写什么。她想为上午会上的话解释一下。
- 沈聿从走廊走过来。他还在介意会上被点名的事。

## 场景气氛
潮湿、安静，咖啡机的声音是唯一的背景音。两个人都不想让步，但也都不想真的吵起来。

## 背景提要
上午的项目会上，林晚提到「后端进度拖了联调」，沈聿当场没说话。周五上线的 deadline 写进了周报。

## 剧本方向
从尴尬开始，允许冲突爆发，但落点应该是某种和解——不一定要解决所有问题。`,
  },
  {
    id: 'scene-17',
    title: '天台上的烟',
    status: 'ended',
    description: '加班后的天台，顾遥说漏了想跳槽的念头，苏黎没有点破。',
    characters: [charById('char-gu-yao'), charById('char-su-li'), charById('char-lin-wan')],
    totalMessages: 97,
    startedAt: iso(60 * 26),
    endedAt: iso(60 * 25),
    lastActivityAt: iso(60 * 25),
    hasUnreadEvents: false,
    setupScript: `# 场景：天台上的烟

## 基本信息
- 时间：晚上九点，加班之后
- 地点：公司天台
- 角色：顾遥（设计师）、苏黎（运营）、林晚（产品经理，中途离开）

## 初始状态
- 顾遥在天台抽烟，刚拒绝了一个猎头的电话。
- 苏黎上来透气，撞见了这一幕。

## 场景气氛
夜风、城市灯光、心照不宣。

## 背景提要
新项目即将立项，顾遥连续两个项目透支，动了跳槽的念头。

## 剧本方向
试探与回避。苏黎想得到信息，顾遥想说又不能说。`,
  },
  {
    id: 'scene-19',
    title: '新项目启动会',
    status: 'draft',
    description: '草稿：新项目第一次全员碰头，四个人的立场各不相同。',
    characters: CHARACTERS,
    totalMessages: 0,
    startedAt: null,
    endedAt: null,
    lastActivityAt: iso(60 * 5),
    hasUnreadEvents: false,
    setupScript: `# 场景：新项目启动会

## 基本信息
- 时间：待定
- 地点：三楼会议室
- 角色：林晚、沈聿、顾遥、苏黎

## 剧本方向
（草稿，尚未定稿）`,
  },
]

// ---- 消息构造辅助 ----
let msgSeq = 0
function msg(
  sceneId: string,
  minutesAgo: number,
  type: Message['type'],
  characterId: string | null,
  content: string,
  innerThought: string | null = null,
  chapter: string | null = null,
  importance = 3,
): Message {
  msgSeq += 1
  const char = characterId ? charById(characterId) : null
  return {
    id: `msg-${sceneId}-${String(msgSeq).padStart(3, '0')}`,
    sceneId,
    timestamp: iso(minutesAgo),
    type,
    characterId,
    characterName: char ? char.name : 'GM',
    characterAvatar: char ? char.avatar : '',
    content,
    innerThought,
    importance,
    chapter,
  }
}

// ---- 消息：场景 18「午后的茶水间」（running，100 条，章节：午后 → 破冰 → 冲突 → 沉默） ----
// 静态历史截止在 iso(1.2)，此后由 LIVE_SCRIPTS（章节「雨幕」）实时续写。
const LIN = 'char-lin-wan'
const SHEN = 'char-shen-yu'
const GU = 'char-gu-yao'
const SU = 'char-su-li'

const MESSAGES_18: Message[] = [
  // —— 午后 ——
  msg('scene-18', 43, 'scene_change', null, '场景：午后的茶水间。下午两点，雨刚停。', null, '午后', 8),
  msg('scene-18', 42.8, 'env', null, '雨刚停，云层的缝隙里漏下一点斜阳。', null, '午后'),
  msg('scene-18', 42.5, 'env', null, '走廊尽头的窗玻璃上还挂着水珠，一颗一颗往下坠。', null, '午后'),
  msg('scene-18', 42.2, 'env', null, '挂钟的秒针走得很响，一格一格，像在给谁计时。', null, '午后'),
  msg('scene-18', 42, 'env', null, '茶水间的窗开着一条缝，风带着湿气吹进来。咖啡机咕噜咕噜地响着。', null, '午后'),
  msg('scene-18', 41.5, 'env', null, '料理台上摆着半盒没吃完的苏打饼干，包装袋敞着口。', null, '午后'),
  msg('scene-18', 41, 'action', LIN, '靠在料理台边上，手里捏着一支笔，没在写什么。', '等他进来，我该怎么开口呢……', '午后'),
  msg('scene-18', 40.5, 'action', LIN, '低头看了一眼手机，屏幕暗着，又扣回台面。', '他没回我消息。', '午后'),
  msg('scene-18', 40, 'action', SHEN, '从走廊那头走过来，脚步声在瓷砖上很清晰。', '她也在。……装作没看见吧。', '午后'),
  msg('scene-18', 39.5, 'action', SHEN, '在门口顿了半步，还是走了进来。', '现在转身走掉，反而显得我在躲她。', '午后'),
  msg('scene-18', 39, 'action', LIN, '把笔夹进笔记本，站直了一点。', null, '午后'),
  msg('scene-18', 38, 'dialogue', SHEN, '「……让一下。」', '不是针对她，只是不想说话。', '午后'),
  msg('scene-18', 37.5, 'env', null, '咖啡机又咕噜了两声，把沉默衬得更响。', null, '午后'),
  msg('scene-18', 37, 'action', LIN, '侧身让开料理台，笔尖在指间转了一圈。', '他果然还在生气。', '午后'),
  msg('scene-18', 36.5, 'action', SHEN, '伸手去拿马克杯，杯柄碰倒了旁边的空杯，又一把扶住。', '手滑什么。', '午后'),
  msg('scene-18', 36, 'dialogue', LIN, '「咖啡机刚煮好，要一杯吗？」', '先试探一下，总不能一直僵着。', '午后'),
  msg('scene-18', 35, 'dialogue', SHEN, '「不用。」', '咖啡是小事，deadline 才是大事。', '午后'),
  msg('scene-18', 34.5, 'action', LIN, '给自己倒了半杯，捧在手里暖着。', '手有点凉。', '午后'),
  msg('scene-18', 34, 'env', null, '咖啡机发出一声长长的排气声，安静下来。', null, '午后'),
  msg('scene-18', 33.5, 'action', SHEN, '洗杯子，水流开得很大，溅湿了袖口也没察觉。', '她到底想说什么。', '午后'),
  // —— 破冰 ——
  msg('scene-18', 33, 'env', null, '窗外的云压得很低，像一块没拧干的抹布。', null, '破冰'),
  msg('scene-18', 32.5, 'action', LIN, '把杯子放下，杯底在台面上磕出轻轻一声。', '再不开口，今天就又这么过去了。', '破冰'),
  msg('scene-18', 32, 'dialogue', LIN, '「上午的会……我不是那个意思。」', '他要是还沉默，我就真不知道怎么办了。', '破冰', 6),
  msg('scene-18', 31.5, 'env', null, '水龙头还开着，没人去关。', null, '破冰'),
  msg('scene-18', 31, 'action', SHEN, '拿起马克杯，又放下，杯底和台面碰出一声轻响。', '不是那个意思？会上当着所有人说「后端进度拖了」，不是那个意思？', '破冰', 5),
  msg('scene-18', 30.5, 'action', LIN, '伸手把水龙头关小了些。', '至少先把水关了，不然谁都没法说话。', '破冰'),
  msg('scene-18', 30, 'dialogue', SHEN, '「嗯。」', '我现在不想吵。', '破冰'),
  msg('scene-18', 29.5, 'env', null, '水珠顺着杯壁滑下来，在台面积成一小圈。', null, '破冰'),
  msg('scene-18', 29, 'dialogue', LIN, '「我是说，联调时间可以再压缩，没有说你们拖进度的意思。」', '至少他肯应声了。', '破冰'),
  msg('scene-18', 28.5, 'action', SHEN, '扯了张纸巾，把台面上的水圈擦掉。', '她在示好。我知道。', '破冰'),
  msg('scene-18', 28, 'dialogue', SHEN, '「上周联调环境还垮了两天，你记得吧。」', '不是翻旧账，是想让她知道三天有多紧。', '破冰', 5),
  msg('scene-18', 27.5, 'dialogue', LIN, '「记得。所以这次我提前约了运维。」', '这个我早有准备。', '破冰', 4),
  msg('scene-18', 27, 'env', null, '楼下传来卷帘门拉开的声音，雨后的街道嘈杂起来。', null, '破冰'),
  msg('scene-18', 26.5, 'action', SHEN, '擦桌子的手慢了半拍。', '她约了运维？这次倒是先想了一步。', '破冰'),
  msg('scene-18', 26, 'dialogue', SHEN, '「压缩到三天。你觉得够吗？」', '三天，两个服务，还要联调。她根本不了解工作量。', '破冰', 6),
  msg('scene-18', 25.5, 'env', null, '咖啡的香气淡下去，空气里的湿气重起来。', null, '破冰'),
  msg('scene-18', 25, 'dialogue', LIN, '「不够的话……我们可以一起对一下排期？」', '别反驳他，先顺着说。', '破冰'),
  msg('scene-18', 24.5, 'action', LIN, '把笔记本翻开，空白的一页朝他那边推了推。', '笔都准备好了，就看他肯不肯坐下来。', '破冰'),
  msg('scene-18', 24, 'action', SHEN, '终于转过身，靠在窗台边，看着她。', '「一起对排期」，上次她也是这么说的，然后呢？', '破冰', 5),
  msg('scene-18', 23.5, 'env', null, '窗台上的绿萝垂下来一条藤，叶尖还挂着雨。', null, '破冰'),
  msg('scene-18', 23, 'dialogue', SHEN, '「上次也是这么说的。」', '说完就后悔了，语气太重。', '破冰', 7),
  msg('scene-18', 22.5, 'action', SHEN, '偏过头去看窗外，下颌线绷着。', '别看她。看她就说不出重话了。', '破冰'),
  msg('scene-18', 22, 'action', LIN, '捏笔的手停住了。', '来了。这句话我等了一下午了。', '破冰', 6),
  // —— 冲突 ——
  msg('scene-18', 21.5, 'env', null, '风把窗缝又推开了一些，呜呜地响。', null, '冲突'),
  msg('scene-18', 21, 'dialogue', LIN, '「上次是运营临时改了需求，不是排期的问题——」', '冷静，别急着辩解。', '冲突', 7),
  msg('scene-18', 20.5, 'dialogue', SHEN, '「每次都有理由。」', '我不是想吵架。我只是太累了。', '冲突', 7),
  msg('scene-18', 20, 'action', LIN, '深吸一口气，把摊开的笔记本合上。', '他这句话，是把上次也算进来了。', '冲突'),
  msg('scene-18', 19.5, 'env', null, '风把窗缝吹得大了些，湿气扑在脸上。', null, '冲突'),
  msg('scene-18', 19, 'dialogue', LIN, '「那你想怎么样？直接说。」', '声音有点抖。控制住。', '冲突', 7),
  msg('scene-18', 18.5, 'action', SHEN, '沉默了几秒，手指在窗台上敲了两下。', '想说「你们产品能不能别什么都答应」，话到嘴边又咽了回去。', '冲突', 6),
  msg('scene-18', 18, 'dialogue', SHEN, '「你们产品，能不能别什么都先答应下来。」', '还是没忍住。', '冲突', 6),
  msg('scene-18', 17.5, 'action', LIN, '被这句话噎了一下，攥笔的指节泛白。', '……好。他终于说出来了。', '冲突'),
  msg('scene-18', 17, 'dialogue', LIN, '「我不是什么都答应。老板压下来的时候，我也在扛。」', '这口气，我也憋了很久了。', '冲突', 6),
  msg('scene-18', 16.5, 'env', null, '两个人都没再说话，只有窗外的水顺着管道滴答。', null, '冲突'),
  msg('scene-18', 16, 'dialogue', SHEN, '「周五上线不了。要延到下周三。」', '说出来反而轻松了。', '冲突', 9),
  msg('scene-18', 15.5, 'action', LIN, '手里转着的笔脱了手，滚到地上。', '来了。最怕听到的一句。', '冲突'),
  msg('scene-18', 15, 'dialogue', LIN, '「下周三……老板那边已经报了周五。」', '完了。周五是写进周报的。', '冲突', 7),
  msg('scene-18', 14.5, 'action', LIN, '弯腰把笔捡起来，指尖蹭到瓷砖上的水渍。', null, '冲突'),
  msg('scene-18', 14, 'dialogue', SHEN, '「那你可以报两个版本。核心功能周五，完整的下周三。」', '这是我能给的最大让步。', '冲突', 8),
  msg('scene-18', 13.5, 'env', null, '冰箱嗡嗡地启动，又安静下来。', null, '冲突'),
  msg('scene-18', 13, 'action', SHEN, '摸出手机，翻出一张排期表，递到她面前。', '昨晚改的。本来没打算给她看。', '冲突', 5),
  msg('scene-18', 12.5, 'action', LIN, '凑近了看，屏幕的光落在两个人之间。', '原来他早就算过了。他不是在赌气。', '冲突', 5),
  msg('scene-18', 12, 'dialogue', LIN, '「性能优化这块……也砍到下周三？」', '问清楚，不能再有第二种理解。', '冲突'),
  msg('scene-18', 11.5, 'dialogue', SHEN, '「砍。周五能跑通主流程就行。」', '她问得很细，是真的想落地。', '冲突'),
  msg('scene-18', 11, 'action', LIN, '盯着杯子里自己的倒影看了一会儿。', '两个版本……其实是在给我台阶下。', '冲突', 5),
  msg('scene-18', 10.5, 'dialogue', LIN, '「……好。我去和老板说。」', '他让步了，我也该让一步。', '冲突', 8),
  msg('scene-18', 10, 'action', SHEN, '点了点头，收回手机，按灭屏幕。', '谈成了。怎么一点都高兴不起来。', '冲突'),
  // —— 沉默 ——
  msg('scene-18', 9.5, 'env', null, '咖啡机彻底冷了，指示灯一闪一闪。', null, '沉默'),
  msg('scene-18', 9, 'action', SHEN, '重新拿起马克杯，接了半杯咖啡。', '事情解决了，为什么气氛更尴尬了。', '沉默'),
  msg('scene-18', 8.5, 'dialogue', SHEN, '「……咖啡还是来一杯吧。」', '算和解吗？不知道。', '沉默', 6),
  msg('scene-18', 8, 'action', LIN, '笑了一下，把笔别回耳后。', '噗。他这个人啊。', '沉默'),
  msg('scene-18', 7.5, 'dialogue', LIN, '「加糖吗？」', '他以前好像是不加糖的。还是加一块？', '沉默'),
  msg('scene-18', 7, 'dialogue', SHEN, '「不加。」', '她记得我不加糖吗？……不记得也正常。', '沉默'),
  msg('scene-18', 6.8, 'env', null, '冰箱门上贴着一张外卖单，边角卷了起来。', null, '沉默'),
  msg('scene-18', 6.5, 'env', null, '走廊里有人走过，说笑声由远及近，又由近及远。', null, '沉默'),
  msg('scene-18', 6, 'action', LIN, '把杯子递过去，指尖碰到杯壁，烫得缩了一下。', '上次这样递咖啡给他，还是上个项目上线那天。', '沉默', 4),
  msg('scene-18', 5.5, 'dialogue', SHEN, '「谢了。」', '她还是老样子，递东西总是双手。', '沉默'),
  msg('scene-18', 5, 'env', null, '斜阳从云缝里收回去，茶水间的灯自动亮了一盏。', null, '沉默'),
  msg('scene-18', 4.8, 'action', SHEN, '把窗台边的绿萝挪开一点，腾出放杯子的位置。', null, '沉默'),
  msg('scene-18', 4.6, 'action', LIN, '也给自己续了半杯，靠着料理台慢慢喝。', null, '沉默'),
  msg('scene-18', 4.4, 'dialogue', LIN, '「顾遥昨天又通宵了，你知道吧。」', '顺便提一句。大家都在硬撑。', '沉默', 4),
  msg('scene-18', 4.2, 'dialogue', SHEN, '「知道。他的提交记录全是凌晨四点。」', '这个人，不要命。', '沉默', 4),
  msg('scene-18', 4, 'dialogue', LIN, '「新项目要是立了，别让他再一个人扛。」', '这句话，也是说给你听的。', '沉默', 5),
  msg('scene-18', 3.8, 'dialogue', SHEN, '「……嗯。」', '她今天的话，怎么句句都接得住。', '沉默'),
  msg('scene-18', 3.6, 'env', null, '楼下的积水里映着一小块天光，被路过的车轮打碎。', null, '沉默'),
  msg('scene-18', 3.4, 'action', SHEN, '捧着咖啡站到窗边，看楼下的积水。', '周五，能做到吗……只能拼了。', '沉默'),
  msg('scene-18', 3.2, 'action', LIN, '也看向窗外，两个人之间隔着一个身位。', '就这样待一会儿也好。', '沉默'),
  msg('scene-18', 3, 'dialogue', LIN, '「上次上线那晚，也是这样的天。」', '提这个干嘛……就是想提。', '沉默', 4),
  msg('scene-18', 2.8, 'dialogue', SHEN, '「那次你请大家喝了奶茶。」', '我那杯的波霸，其实我不爱吃。', '沉默'),
  msg('scene-18', 2.6, 'dialogue', LIN, '「你那杯没喝完，我记得。」', '我居然还记得这个。', '沉默', 4),
  msg('scene-18', 2.5, 'action', LIN, '把手里的杯子捧紧了些，没再说话。', '沉默也不难受了。', '沉默'),
  msg('scene-18', 2.4, 'action', SHEN, '嘴角动了一下，算是笑了。', '她记得。', '沉默'),
  msg('scene-18', 2.2, 'env', null, '远处传来闷雷，像是要下第二场雨。', null, '沉默'),
  msg('scene-18', 2, 'dialogue', LIN, '「下周三，我盯紧一点联调。」', '这次说到做到。', '沉默', 5),
  msg('scene-18', 1.8, 'dialogue', SHEN, '「嗯。一起。」', '「一起」这个词，说出来居然不难。', '沉默', 7),
  msg('scene-18', 1.6, 'env', null, '云又厚了一层，光线暗下来，像戏院落下一道幕。', null, '沉默'),
  msg('scene-18', 1.5, 'action', LIN, '把笔记本重新翻开，写下「周三·联调」四个字。', '这次写下来的，就一定要做到。', '沉默', 4),
  msg('scene-18', 1.4, 'action', SHEN, '瞥见那行字，没说话，把杯里的咖啡喝完了。', '字写得挺好看。……想什么呢。', '沉默'),
  msg('scene-18', 1.3, 'env', null, '第一滴雨落在窗台上，很轻，像有人叩了一下门。', null, '沉默'),
  msg('scene-18', 1.2, 'dialogue', LIN, '「要下了。」', '下吧。下完这场，就都好了。', '沉默'),
]

// ---- 消息：场景 17「天台上的烟」（ended，97 条，章节：夜风 → 试探 → 旧事 → 心照不宣） ----
const MESSAGES_17: Message[] = [
  // —— 夜风 ——
  msg('scene-17', 60 * 26, 'scene_change', null, '场景：天台上的烟。晚上九点，加班之后。', null, '夜风', 8),
  msg('scene-17', 60 * 26 - 0.5, 'env', null, '天台的灯坏了半个月，只有对面楼的霓虹漏过来一点光。', null, '夜风'),
  msg('scene-17', 60 * 26 - 1, 'env', null, '霓虹每三秒变一次颜色，红，蓝，再红。', null, '夜风'),
  msg('scene-17', 60 * 26 - 1.5, 'action', GU, '把烟头按灭在栏杆上，又点了一根。', '猎头的电话，第三个了。开的价格……说不心动是假的。', '夜风', 5),
  msg('scene-17', 60 * 26 - 2, 'action', GU, '把手机掏出来看了一眼，又扣在栏杆上。', '他又发来消息，开价又往上加了一截。', '夜风'),
  msg('scene-17', 60 * 26 - 2.5, 'env', null, '风从水箱后面绕过来，带着白天晒热的铁锈味。', null, '夜风'),
  msg('scene-17', 60 * 26 - 3, 'action', GU, '抬脚把地上的空易拉罐拨到一边，哐当一声。', '谁喝完的也不知道收。', '夜风'),
  msg('scene-17', 60 * 26 - 3.5, 'action', GU, '脱下西装外套搭在栏杆上，松了松领口。', '两个项目，七个月。我到底在图什么。', '夜风', 4),
  msg('scene-17', 60 * 26 - 4, 'env', null, '楼梯间传来门轴转动的声音，很慢。', null, '夜风'),
  msg('scene-17', 60 * 26 - 4.5, 'action', SU, '推开天台的门，风灌进来，她眯了眯眼。', '果然在这儿。全公司只有他抽烟是这个姿势。', '夜风'),
  msg('scene-17', 60 * 26 - 5, 'action', SU, '在门口站了两秒，让眼睛适应黑暗。', '烟味这么重。他今晚抽得很凶。', '夜风'),
  msg('scene-17', 60 * 26 - 5.5, 'dialogue', SU, '「一个人躲这儿，稿子改完了？」', '先不点破，看他怎么说。', '夜风'),
  msg('scene-17', 60 * 26 - 6, 'action', GU, '没回头，朝角落的烟灰缸抬了抬下巴。', '她走路没声音，猫一样。', '夜风'),
  msg('scene-17', 60 * 26 - 6.5, 'dialogue', GU, '「改完了。林晚又提了三条意见。」', '她这时候上来，不会是巧合。', '夜风'),
  msg('scene-17', 60 * 26 - 7, 'env', null, '霓虹转成蓝色，把两个人的影子染冷了一层。', null, '夜风'),
  msg('scene-17', 60 * 26 - 7.5, 'dialogue', SU, '「她的意见你听听就好，别往心里去。」', '先站到他这边，话才聊得下去。', '夜风'),
  msg('scene-17', 60 * 26 - 8, 'action', GU, '笑了一声，烟灰被风卷走。', '不往心里去……我两个项目都是这么过来的。', '夜风'),
  msg('scene-17', 60 * 26 - 8.5, 'action', SU, '走近两步，也趴到栏杆上，隔着一个人的距离。', '先陪他看会儿夜景，急不得。', '夜风'),
  msg('scene-17', 60 * 26 - 9, 'action', SU, '摸出一颗薄荷糖，剥开含上。', '烟味太呛，压一压。', '夜风'),
  msg('scene-17', 60 * 26 - 9.5, 'dialogue', SU, '「来一颗？比烟好。」', '聊点轻的。', '夜风'),
  msg('scene-17', 60 * 26 - 10, 'dialogue', GU, '「不了。」', '她想问什么，我大概知道。', '夜风'),
  msg('scene-17', 60 * 26 - 10.5, 'env', null, '天台上堆着的旧展板被风吹得轻轻晃。', null, '夜风'),
  // —— 试探 ——
  msg('scene-17', 60 * 26 - 11, 'env', null, '远处高架上的车流不断，红色的尾灯连成一条线。', null, '试探'),
  msg('scene-17', 60 * 26 - 11.5, 'dialogue', GU, '「你说，人为什么要一直做同一种事呢？」', '试探一下她的反应。', '试探', 7),
  msg('scene-17', 60 * 26 - 12, 'action', SU, '靠在门边的墙上，离他三步远。', '来了。这句话我在他上个项目结束时也听过。', '试探', 6),
  msg('scene-17', 60 * 26 - 12.5, 'dialogue', SU, '「因为换一种事做，要从头再来。你舍得吗？」', '把球踢回去。', '试探', 7),
  msg('scene-17', 60 * 26 - 13, 'action', GU, '把烟摁灭，没点新的，手指在烟盒上敲。', '她果然不接招。', '试探'),
  msg('scene-17', 60 * 26 - 13.5, 'dialogue', GU, '「舍不得的东西多了。」', '新项目、团队……还有她。想到这儿就有点烦。', '试探', 7),
  msg('scene-17', 60 * 26 - 14, 'env', null, '楼下便利店的灯光在积水里晃。夜风把云推开了，露出半个月亮。', null, '试探'),
  msg('scene-17', 60 * 26 - 14.5, 'dialogue', SU, '「月亮出来了。」', '给他一点沉默的余地。', '试探'),
  msg('scene-17', 60 * 26 - 15, 'action', GU, '抬头看了一眼，没说话。', '半个月亮，像一张没画完的稿。', '试探'),
  msg('scene-17', 60 * 26 - 15.5, 'dialogue', GU, '「你大晚上上天台，就为了看月亮？」', '她到底想干什么。', '试探'),
  msg('scene-17', 60 * 26 - 16, 'dialogue', SU, '「透气。顺便看看你死没死。」', '话说重点，心放软点。', '试探'),
  msg('scene-17', 60 * 26 - 16.5, 'action', GU, '被她逗笑了，今晚第一次。', '这人。', '试探'),
  msg('scene-17', 60 * 26 - 17, 'dialogue', SU, '「听说新项目下周立项。」', '该往正题上引了。', '试探', 4),
  msg('scene-17', 60 * 26 - 17.5, 'dialogue', GU, '「听说了。」', '来了。', '试探'),
  msg('scene-17', 60 * 26 - 18, 'dialogue', SU, '「你没什么想法？」', '再问深一点。', '试探'),
  msg('scene-17', 60 * 26 - 18.5, 'action', GU, '把烟盒攥扁，又慢慢抚平。', '想法？想法就是有人开了双倍的价。', '试探'),
  msg('scene-17', 60 * 26 - 19, 'dialogue', GU, '「想法有啊。想休个假。」', '说了半句真话。', '试探', 5),
  msg('scene-17', 60 * 26 - 19.5, 'dialogue', SU, '「好啊，立项之后就批你。」', '他话里有话。', '试探'),
  msg('scene-17', 60 * 26 - 20, 'env', null, '楼梯间又有了脚步声，这次是急的。', null, '试探'),
  msg('scene-17', 60 * 26 - 20.5, 'action', LIN, '推门探进半个身子，挥了挥手里的手机。', '打扰他们了吗？算了，正事要紧。', '试探'),
  msg('scene-17', 60 * 26 - 21, 'dialogue', LIN, '「顾遥，主视觉那版定了吗？老板明早要看。」', '天台……他俩在聊什么，气氛有点怪。', '试探'),
  msg('scene-17', 60 * 26 - 21.5, 'dialogue', GU, '「定了，在我电脑里，你自己拿。」', '正好，不想继续这个话题了。', '试探'),
  msg('scene-17', 60 * 26 - 22, 'action', LIN, '比了个 OK 的手势，转身要走，又停住。', '这气氛……我是不是来得不是时候。', '试探'),
  msg('scene-17', 60 * 26 - 22.5, 'dialogue', LIN, '「你们……继续？」', null, '试探'),
  msg('scene-17', 60 * 26 - 23, 'dialogue', SU, '「去吧，文件在我桌上第二层。」', '快走吧，正聊到关键处。', '试探'),
  msg('scene-17', 60 * 26 - 23.5, 'action', LIN, '点点头，带上门走了，脚步声很快消失在楼梯间。', '顾遥今天话好少。回头问问他。', '试探'),
  msg('scene-17', 60 * 26 - 24, 'env', null, '门轴吱呀一声合上，天台又只剩风声。', null, '试探'),
  // —— 旧事 ——
  msg('scene-17', 60 * 26 - 24.5, 'dialogue', SU, '「还记得『清河』那个项目吗？」', '换个方向试试。', '旧事'),
  msg('scene-17', 60 * 26 - 25, 'dialogue', GU, '「怎么不记得。上线前夜，服务器就躺在楼下机房。」', '那晚的风，也是这个味道。', '旧事'),
  msg('scene-17', 60 * 26 - 25.5, 'action', SU, '笑了一下，往他那边挪了半步。', '他肯接话了。', '旧事'),
  msg('scene-17', 60 * 26 - 26, 'dialogue', SU, '「那晚你一个人改图改到早上六点。」', '我记得的，比他以为的多。', '旧事'),
  msg('scene-17', 60 * 26 - 26.5, 'dialogue', GU, '「你不也陪着。那碗泡面还是你泡的。」', '她居然还记得这个。', '旧事'),
  msg('scene-17', 60 * 26 - 27, 'env', null, '月亮升高了一点，水箱的影子斜过来。', null, '旧事'),
  msg('scene-17', 60 * 26 - 27.5, 'dialogue', SU, '「所以我知道你能扛。但人不能一直靠扛。」', '这句话，是说给今晚的他听的。', '旧事', 6),
  msg('scene-17', 60 * 26 - 28, 'action', GU, '沉默了很久，烟头在黑暗里明了一下，又暗下去。', '她到底知道多少？', '旧事'),
  msg('scene-17', 60 * 26 - 28.5, 'dialogue', GU, '「苏黎。」', '要不要说？', '旧事'),
  msg('scene-17', 60 * 26 - 29, 'dialogue', SU, '「嗯？」', '心跳快了半拍。稳住。', '旧事'),
  msg('scene-17', 60 * 26 - 29.5, 'action', GU, '张了张嘴，最后只是摆了摆手。', '算了。说出口，就回不去了。', '旧事', 7),
  msg('scene-17', 60 * 26 - 30, 'dialogue', GU, '「……没什么。风挺舒服的。」', '懦夫。', '旧事', 5),
  msg('scene-17', 60 * 26 - 30.5, 'action', SU, '看了他两秒，没追问。', '他刚才差一点就说了。差一点。', '旧事', 6),
  msg('scene-17', 60 * 26 - 31, 'env', null, '霓虹恰好熄了一轮，天台暗下来，只剩月光。', null, '旧事'),
  msg('scene-17', 60 * 26 - 31.5, 'dialogue', SU, '「顾遥，我不绕弯子了。」', '再等下去，他今晚什么都不会说。', '旧事', 6),
  // —— 心照不宣 ——
  msg('scene-17', 60 * 26 - 32, 'dialogue', SU, '「新项目要立了。我想把你放在主设计上。」', '直接给足他位置，比挽留有用。', '心照不宣', 7),
  msg('scene-17', 60 * 26 - 32.5, 'env', null, '风小下去，城市的声音浮上来，很远。', null, '心照不宣'),
  msg('scene-17', 60 * 26 - 33, 'action', GU, '把烟按灭了，这次没有再点。', '她知道了。她绝对知道了。……但她没说破。', '心照不宣', 9),
  msg('scene-17', 60 * 26 - 33.5, 'action', GU, '把攥扁的烟盒塞回口袋，动作很慢。', '主设计。她真敢给。', '心照不宣'),
  msg('scene-17', 60 * 26 - 34, 'dialogue', GU, '「你知道主设计意味着什么吧。上一个坐这个位置的人，离职了。」', '再确认一次，她不是随口说说。', '心照不宣', 5),
  msg('scene-17', 60 * 26 - 34.5, 'dialogue', SU, '「我知道。所以这次给你配两个人，沈聿那边的接口也优先排。」', '这些是提前想好的，不是临场编的。', '心照不宣', 5),
  msg('scene-17', 60 * 26 - 35, 'env', null, '楼下便利店关了灯，街道暗了一格。', null, '心照不宣'),
  msg('scene-17', 60 * 26 - 35.5, 'action', GU, '转过身，第一次正眼看她。', '她连这个都准备了。什么时候？', '心照不宣'),
  msg('scene-17', 60 * 26 - 36, 'dialogue', GU, '「……行。但别让我一个人扛。」', '这句话说出口，好像也没那么想走了。', '心照不宣', 9),
  msg('scene-17', 60 * 26 - 36.5, 'dialogue', SU, '「这次不会。」', '至少今晚不会。明天的事，明天再说。', '心照不宣', 7),
  msg('scene-17', 60 * 26 - 37, 'action', SU, '伸出手。', '空口无凭，得有个仪式。', '心照不宣', 5),
  msg('scene-17', 60 * 26 - 37.5, 'action', GU, '看了一眼，握上去，很短的一下。', '她的手很凉。', '心照不宣', 6),
  msg('scene-17', 60 * 26 - 38, 'env', null, '霓虹重新亮起来，红色的光扫过天台。', null, '心照不宣'),
  msg('scene-17', 60 * 26 - 38.5, 'env', null, '风停了。两个人各自看着不同的方向，谁都没有先走。', null, '心照不宣'),
  msg('scene-17', 60 * 26 - 39, 'dialogue', GU, '「立项会什么时候？」', '既然留下，就把事情做实。', '心照不宣'),
  msg('scene-17', 60 * 26 - 39.5, 'dialogue', SU, '「下周三之前。视觉方案，到时候你来讲。」', '他肯问，就是答应了。', '心照不宣', 4),
  msg('scene-17', 60 * 26 - 40, 'dialogue', GU, '「行。我这两天把框架拉出来。」', '手已经有点痒了，想画图。', '心照不宣'),
  msg('scene-17', 60 * 26 - 40.5, 'action', SU, '点点头，把散下来的头发别到耳后。', '成了。今晚没白上来。', '心照不宣'),
  msg('scene-17', 60 * 26 - 41, 'env', null, '月亮被新涌上来的云遮住一半，光线软下去。', null, '心照不宣'),
  msg('scene-17', 60 * 26 - 41.5, 'dialogue', GU, '「烟灰缸满了。明天我带东西上来收拾一下。」', '总得找点话说。', '心照不宣'),
  msg('scene-17', 60 * 26 - 42, 'dialogue', SU, '「顺便把灯也报修了，坏了半个月了。」', '他愿意管天台的事了，好兆头。', '心照不宣'),
  msg('scene-17', 60 * 26 - 42.5, 'action', GU, '拎起栏杆上的外套，抖了抖。', '那条消息，回去就删。', '心照不宣', 5),
  msg('scene-17', 60 * 26 - 43, 'dialogue', GU, '「走吧，下去。再待要着凉了。」', '今天，先到这儿。', '心照不宣'),
  msg('scene-17', 60 * 26 - 43.5, 'action', SU, '先一步走到门边，替他拉开门。', '这一步，让他先欠着。……开玩笑的。', '心照不宣'),
  msg('scene-17', 60 * 26 - 44, 'env', null, '楼道里的声控灯应声而亮，暖黄色的一小片。', null, '心照不宣'),
  msg('scene-17', 60 * 26 - 44.5, 'action', GU, '走进光里，又回头看了一眼天台。', '那半根没抽完的烟，就留在那儿吧。', '心照不宣', 4),
  msg('scene-17', 60 * 26 - 45, 'dialogue', SU, '「顾遥。」', '最后叮嘱一句。', '心照不宣'),
  msg('scene-17', 60 * 26 - 45.5, 'dialogue', GU, '「又干嘛。」', '她还要说什么。', '心照不宣'),
  msg('scene-17', 60 * 26 - 46, 'dialogue', SU, '「主视觉明早九点，别迟到。」', '有正事收尾，今晚就不算只是叙旧。', '心照不宣'),
  msg('scene-17', 60 * 26 - 46.5, 'action', GU, '摆摆手，身影拐进楼梯间。', '知道了。啰嗦。', '心照不宣'),
  msg('scene-17', 60 * 26 - 47, 'env', null, '天台上，那半根烟的火星闪了一下，彻底灭了。', null, '心照不宣'),
  msg('scene-17', 60 * 26 - 47.5, 'env', null, '月光落在空下来的栏杆上，像戏散后没撤的景。', null, '心照不宣'),
  msg('scene-17', 60 * 26 - 48, 'scene_change', null, '场景落幕：夜风停了，有些话没有说出口，也不必说出口。', null, '心照不宣', 8),
]

export const MESSAGES: Record<string, Message[]> = {
  'scene-18': MESSAGES_18,
  'scene-17': MESSAGES_17,
  'scene-19': [],
}

// ---- 角色内部状态（浮动仪表盘，§5.4.2） ----
export const CHARACTER_STATES: Record<string, Record<string, CharacterState>> = {
  'scene-18': {
    [LIN]: {
      characterId: LIN,
      emotion: '😊 平静',
      innerThought: '就这样待一会儿也好。',
      lastMemoryActivity: { type: 'recall', content: '想起上个项目上线那天，也是她递的咖啡。' },
    },
    [SHEN]: {
      characterId: SHEN,
      emotion: '🤔 犹豫',
      innerThought: '「一起」这个词，说出来居然不难。',
      lastMemoryActivity: { type: 'memorize', content: '记下：她说下周三会盯紧联调。这次或许可以信。' },
    },
  },
  'scene-17': {
    [GU]: {
      characterId: GU,
      emotion: '🤔 犹豫',
      innerThought: '这句话说出口，好像也没那么想走了。',
      lastMemoryActivity: { type: 'memorize', content: '记下：苏黎说「这次不会」让我一个人扛。' },
    },
    [SU]: {
      characterId: SU,
      emotion: '😊 平静',
      innerThought: '至少今晚不会。明天的事，明天再说。',
      lastMemoryActivity: { type: 'recall', content: '想起上个项目结束时，顾遥也说过同样的话。' },
    },
    [LIN]: {
      characterId: LIN,
      emotion: '😟 担心',
      innerThought: '顾遥今天话好少。回头问问他。',
      lastMemoryActivity: null,
    },
  },
  'scene-19': {},
}

/** 直播消息到达时更新角色内部状态，返回 { [characterId]: state } 补丁 */
export function charStatePatch(
  sceneId: string,
  characterId: string,
  innerThought: string,
): Record<string, CharacterState> {
  const states = (CHARACTER_STATES[sceneId] ??= {})
  const prev = states[characterId]
  const next: CharacterState = {
    characterId,
    emotion: prev?.emotion ?? '😊 平静',
    innerThought,
    lastMemoryActivity: prev?.lastMemoryActivity ?? null,
  }
  states[characterId] = next
  return { [characterId]: next }
}

// ---- 场景阶段摘要（补课模式，§5.4.6） ----
export const SCENE_SUMMARIES: Record<string, SceneSummary> = {
  'scene-18': {
    sceneId: 'scene-18',
    generatedAt: iso(10),
    bullets: [
      '林晚和沈聿就项目 deadline 发生了分歧。',
      '林晚试图缓和气氛，但沈聿一开始没接话。',
      '沈聿提出两个版本的折中方案，林晚接受并去找老板沟通。',
      '两人达成和解，目前并肩看着窗外，沉默但不再对立。',
    ],
  },
  'scene-17': {
    sceneId: 'scene-17',
    generatedAt: iso(60 * 25),
    bullets: [
      '顾遥在天台抽烟，接完猎头电话后心事重重。',
      '苏黎上天台透气，两人互相试探，都没有点破。',
      '苏黎提出让顾遥负责新项目主设计，顾遥留下。',
      '场景落幕：有些话没有说出口，也不必说出口。',
    ],
  },
}

// ---- 日记 ×10 ----
let diarySeq = 0
function diary(
  characterId: string,
  sceneId: string,
  minutesAgo: number,
  content: string,
  isImportant = false,
  note = '',
): DiaryEntry {
  diarySeq += 1
  const scene = SCENES.find((s) => s.id === sceneId)!
  return {
    id: `diary-${String(diarySeq).padStart(2, '0')}`,
    characterId,
    sceneId,
    sceneTitle: scene.title,
    createdAt: iso(minutesAgo),
    content,
    wordCount: content.length,
    isImportant,
    note,
  }
}

export const DIARIES: DiaryEntry[] = [
  diary(
    LIN,
    'scene-18',
    60 * 3,
    '今天下午在茶水间，我终于和沈聿把 deadline 的事说开了。他提出两个版本的方案时，我其实松了口气——原来他不是要和我对立，只是需要被理解工作量。以后开会说话要更小心，「后端拖了进度」这种话，太伤人了。下周三的联调，我一定盯紧。',
    true,
    '和沈聿和解的关键节点',
  ),
  diary(
    LIN,
    'scene-17',
    60 * 25,
    '晚上去天台找顾遥定主视觉，他和苏黎在那里说话，气氛有点怪。顾遥今天话很少，眼神也飘。是不是最近太累了？两个项目连轴转，换谁都受不了。回头找个时间问问他。',
  ),
  diary(
    SHEN,
    'scene-18',
    60 * 3,
    '茶水间。本来不想说话的。但她问我要不要咖啡的时候，语气小心得过分。说了「上次也是这么说的」，说完就后悔了。不过最后还是说开了：周五核心版，下周三完整版。她说「一起」的时候，我居然觉得这个词不难说出口。记下来：她不记得我不加糖，但她记得递东西用双手。',
    true,
  ),
  diary(
    SHEN,
    'scene-17',
    60 * 28,
    '顾遥最近不对劲。提交记录的时间越来越晚，评审会上一句话不说。天台上他和苏黎聊了什么我不知道，但回来时他的表情比上去之前松了一点。新项目如果真让他做主设计，得有人盯着别让他又一个人通宵。',
  ),
  diary(
    GU,
    'scene-17',
    60 * 25,
    '猎头第三个电话了。开的价格比我预想的高。挂了电话在天台抽烟，被苏黎撞见了。她什么都没问，又好像什么都问了。「新项目让你做主设计」——她真敢说，我也真想接。我说「别让我一个人扛」，她说「这次不会」。姑且信一次。',
    true,
    '跳槽念头的转折点',
  ),
  diary(
    GU,
    'scene-17',
    60 * 26,
    '林晚上来拿主视觉的时候，我差点以为她要问什么。还好她只是拿文件。这个项目做完，我想休个长假。如果还有「做完」的话。',
  ),
  diary(
    SU,
    'scene-17',
    60 * 25,
    '天台上确认了：顾遥动了走的心思。我没有点破，点了主设计的位置给他。他需要被需要，这比加薪有用。当然，话不能只说到这里，下周的立项会我得真的把位置给他落实。留住人，靠的是事，不是情。',
  ),
  diary(
    SU,
    'scene-17',
    60 * 24,
    '林晚中途上天台拿文件，风风火火的。她大概没看出来我们在聊什么，看出来了也会装作没看出来。她是那种把担心写在脸上、把体贴藏在动作里的人。',
  ),
  diary(LIN, 'scene-18', 60 * 50, '上午的会开砸了。当着所有人说「后端进度拖了联调」，沈聿当场没说话，脸色沉下去。我怎么能那么说呢。下午得找个机会解释。', false, '冲突的起点'),
  diary(SHEN, 'scene-18', 60 * 49, '会上被点名了。不想辩解，辩解没用。周五上线，两个服务要联调，她根本不懂这意味着什么。下午去茶水间躲一会儿。'),
]

// ---- 记忆条目 ×20 ----
let memSeq = 0
function memory(
  characterId: string,
  content: string,
  tags: string[],
  importance: number,
  minutesAgo: number,
  isActive = true,
): MemoryItem {
  memSeq += 1
  return {
    id: `mem-${String(memSeq).padStart(2, '0')}`,
    characterId,
    content,
    tags,
    importance,
    createdAt: iso(minutesAgo + 30),
    updatedAt: iso(minutesAgo),
    isActive,
  }
}

export const MEMORIES: MemoryItem[] = [
  // 林晚
  memory(LIN, '沈聿喝咖啡不加糖。', ['沈聿', '习惯'], 3, 60 * 24 * 30),
  memory(LIN, '上午开会时我说「后端进度拖了」，沈聿当场没说话，但他很介意。', ['沈聿', '冲突'], 5, 60 * 5),
  memory(LIN, '沈聿提出两个版本的方案：核心功能周五，完整版下周三。这是他的让步。', ['沈聿', 'deadline'], 5, 60 * 2),
  memory(LIN, '上次和沈聿在茶水间聊 deadline 也发生过分歧，最后是运营改需求收的场。', ['沈聿', '茶水间'], 4, 60 * 24 * 20, false),
  memory(LIN, '顾遥最近话很少，天台上他和苏黎聊过之后气氛有点怪。', ['顾遥', '担心'], 4, 60 * 24),
  // 沈聿
  memory(SHEN, '林晚递东西总是用双手。', ['林晚', '细节'], 3, 60 * 2),
  memory(SHEN, '林晚在大会上说话不过脑子，但她会事后补救。', ['林晚', '性格'], 4, 60 * 5),
  memory(SHEN, '周五只能上核心功能，完整版要下周三。已经和她说清楚了。', ['deadline', '联调'], 5, 60 * 2),
  memory(SHEN, '顾遥连续两个项目通宵，不能让他再一个人扛。', ['顾遥', '担心'], 4, 60 * 24),
  memory(SHEN, '产品侧的排期承诺不可靠，上次说「一起对排期」也没兑现。', ['林晚', '排期'], 3, 60 * 24 * 20, false),
  // 顾遥
  memory(GU, '猎头开了三次价，一次比一次高。我还没答应。', ['跳槽', '猎头'], 5, 60 * 24),
  memory(GU, '苏黎知道我想走，但她没说破，还把主设计的位置给了我。', ['苏黎', '新项目'], 5, 60 * 25),
  memory(GU, '林晚提意见很直接，但都是对事不对人。', ['林晚', '工作方式'], 3, 60 * 26),
  memory(GU, '连续两个项目都是我一个人扛下来的，通宵了一周。', ['透支', '工作'], 4, 60 * 24 * 40),
  memory(GU, '苏黎说「这次不会」让我一个人扛。我选择信她一次。', ['苏黎', '承诺'], 4, 60 * 25),
  // 苏黎
  memory(SU, '顾遥动了跳槽的心思，猎头已经联系他至少三次。', ['顾遥', '跳槽'], 5, 60 * 25),
  memory(SU, '顾遥需要被需要。给他主设计的位置比挽留的话有用。', ['顾遥', '策略'], 4, 60 * 25),
  memory(SU, '林晚把担心写在脸上，把体贴藏在动作里。', ['林晚', '观察'], 3, 60 * 24),
  memory(SU, '新项目立项会要尽快开，把顾遥的位置落实，话不能只说一半。', ['新项目', '顾遥'], 5, 60 * 20),
  memory(SU, '沈聿话少但可靠，技术上他说不行就是真的不行。', ['沈聿', '信任'], 4, 60 * 24 * 15),
]

// ---- 通知事件 ----
export const NOTIFICATIONS: NotificationEvent[] = [
  {
    id: 'ntf-1',
    type: 'milestone',
    sceneId: 'scene-18',
    sceneTitle: '午后的茶水间',
    message: '关键记忆回溯：林晚想起了与沈聿的上一次分歧',
    timestamp: iso(30),
    isRead: true,
  },
  {
    id: 'ntf-2',
    type: 'milestone',
    sceneId: 'scene-18',
    sceneTitle: '午后的茶水间',
    message: '情绪阈值触发：沈聿 由「烦躁」转为「平静」',
    timestamp: iso(11),
    isRead: false,
  },
  {
    id: 'ntf-3',
    type: 'scene_ended',
    sceneId: 'scene-17',
    sceneTitle: '天台上的烟',
    message: '场景已落幕：有些话没有说出口，也不必说出口',
    timestamp: iso(60 * 25),
    isRead: false,
  },
]

// ---- 角色控制台：聊天历史 ----
let chatSeq = 0
function chat(characterId: string, role: 'user' | 'character', content: string, minutesAgo: number): ChatMessage {
  chatSeq += 1
  return { id: `chat-${String(chatSeq).padStart(3, '0')}`, characterId, role, content, timestamp: iso(minutesAgo) }
}

export const CHAT_HISTORY: Record<string, ChatMessage[]> = {
  [LIN]: [
    chat(LIN, 'user', '今天茶水间那场戏，你演得挺克制的。', 60 * 4),
    chat(LIN, 'character', '克制吗……其实递咖啡的时候手都在抖。不过你说我演得好，我有点开心。毕竟是你写的我们。', 60 * 4 - 1),
    chat(LIN, 'user', '下周联调打算怎么盯？', 60 * 4 - 2),
    chat(LIN, 'character', '这次说到了就要做到。我已经把每天的联调节点列出来了，你别偷改我的剧本就行。', 60 * 4 - 3),
  ],
  [SHEN]: [
    chat(SHEN, 'user', '「嗯。一起。」这句是你自己想说的吗？', 60 * 6),
    chat(SHEN, 'character', '……是。话到嘴边就出来了。你们写剧本的人大概不信，我们有时候也会超出你们的预期。', 60 * 6 - 1),
  ],
  [GU]: [chat(GU, 'user', '还走吗？', 60 * 20), chat(GU, 'character', '不走了。至少这个项目做完之前不走。你和苏黎商量好的吧，一个唱红脸一个唱白脸。', 60 * 20 - 1)],
  [SU]: [],
}

// ---- 角色控制台：聊天模拟回复（第四面墙 开/关 两套语料） ----
export const CHAT_REPLIES: Record<string, { fourthWall: string[]; inWorld: string[] }> = {
  [LIN]: [
    {
      fourthWall: [
        '你是在问我本人，还是问「林晚」？算了，答案一样：我不后悔说开，只后悔在会上那么说。',
        '你写我的时候能不能少让我捏那支笔？转了一下午，手都酸了。……开玩笑的，那支笔挺好的。',
        '下周的联调我盯着，你盯着我就行。别又把我写成只会缓和气氛的人。',
      ],
      inWorld: [
        '哎？你怎么知道茶水间的事……哦，是苏黎说的吧。没什么大事，就是说开了而已。',
        '下周联调你要是路过，可以来看看我们吵架——开玩笑的，现在不吵了。',
        '谢谢关心。他真的只是话少，人很好的。你别听上午会上那些。',
      ],
    },
  ][0],
  [SHEN]: [
    {
      fourthWall: [
        '嗯。……你特意开这个对话，不会只是想听我「嗯」吧。',
        '下一场戏安排我做什么？先说好，通宵的戏我不接，顾遥那种戏路我走不了。',
        '她记不记得我不加糖，不重要。……你刚才是不是想写「重要」？别。',
      ],
      inWorld: [
        '咖啡不加糖。谢谢。',
        '联调的事，问她。她说一起盯，那就一起盯。',
        '……还有事吗？没事我回去改代码了。',
      ],
    },
  ][0],
  [GU]: [
    {
      fourthWall: [
        '猎头那条线是你埋的吧？行行行，我不走，看你后面怎么写。',
        '主设计这个位置我接了。下个项目别让我通宵，听见没，作者大人。',
        '苏黎那个人，比我聪明。你写她的时候偏心一点也没关系，我不介意。',
      ],
      inWorld: [
        '哟，新同事？坐。抽烟吗？……哦你不抽，那我自己来。',
        '跳槽？谁说的，没有的事。苏黎那张嘴……算了，她答应我的事做到了就行。',
        '主视觉在改了在改了，别催。林晚催完你催，你们约好的吧。',
      ],
    },
  ][0],
  [SU]: [
    {
      fourthWall: [
        '你想聊顾遥的事？我知道的比你想象的多一点——毕竟你只写了我看到的，没写我猜到的。',
        '放心，立项会上我会把主设计的位置给他落实。我说话算话，这点你可以写进设定里。',
        '我很好奇，在你原本的剧本里，我点破他了吗？……别告诉我，我想留点悬念。',
      ],
      inWorld: [
        '消息挺灵通的嘛。坐，想喝什么？我请。',
        '顾遥的事你别操心，我心里有数。该给他的位置，一个都不会少。',
        '项目上的事，会上说。私下嘛……聊聊天气怎么样？今晚风挺舒服的。',
      ],
    },
  ][0],
}

// ---- 记忆整理（审计 Tab）的开场「思考」 ----
export const AUDIT_THOUGHTS: Record<string, { thought: string; memoryId: string; proposal: string; newContent: string }> = {
  [LIN]: {
    thought: '「我记得上次和沈聿在茶水间聊 deadline，最后不欢而散……但那个印象好像已经不太准确了，我应该更新一下。」',
    memoryId: 'mem-4',
    proposal: '我想把这条记忆改成：上次分歧其实以和解收场，他提出了两个版本的方案。你觉得呢？',
    newContent: '上次和沈聿在茶水间的分歧，以和解收场：他提出了两个版本的折中方案。',
  },
  [SHEN]: {
    thought: '「我一直记着『产品侧的排期承诺不可靠』……但今天她说要一起盯联调。这条记忆，是不是该改改了？」',
    memoryId: 'mem-10',
    proposal: '我想把它更新为：她这次主动提出一起盯联调，或许可以再信一次。可以吗？',
    newContent: '林晚这次主动提出一起盯联调。排期承诺或许可以再信一次。',
  },
  [GU]: {
    thought: '「『连续两个项目都是我一个人扛』……这条还留着吗？苏黎说这次不会。我有点想信她。」',
    memoryId: 'mem-14',
    proposal: '要不要把它改成：过去是我一个人扛，但这次苏黎承诺不会了？',
    newContent: '过去连续两个项目是我一个人扛的，但苏黎承诺这次不会。',
  },
  [SU]: {
    thought: '「我记下了顾遥想跳槽。但他已经答应留下了，这条记忆是不是该降降重要性？」',
    memoryId: 'mem-16',
    proposal: '我想把这条的重要性调低，标注为「已缓解」。你同意吗？',
    newContent: '顾遥曾动过跳槽的心思，但在主设计承诺后已缓解。',
  },
}

// ---- 舞台监督：编剧 Agent 语料 ----
export const PLAYWRIGHT_OPENING =
  '你好，我是编剧。这个场景想做成什么样？说说你的想法——比如谁和谁、在哪里、气氛如何、希望发生什么。'

export const PLAYWRIGHT_REPLIES: string[] = [
  '明白了。两个人、一个狭小的公共空间、一层没说破的矛盾——这是很好的张力来源。我再确认一下：你希望冲突当场爆发，还是压在表面之下？',
  '好建议。我把「雨刚停」作为开场环境：湿气、半开的窗、咖啡机的声音，都能托住这种欲言又止的气氛。角色的初始状态需要各自带着「想说又没说的话」上场。',
  '关于落点，我建议不收成彻底的和解——留一点没解决的东西，下一场戏才有接着写的空间。比如达成一个「暂时的共识」，但各自心里都有保留。',
  '都记下了。你可以点「生成草稿」，我会把目前讨论的内容整理成结构化的场景文档，填到右侧预览区。',
]

// ---- WebSocket 模拟：直播推送脚本（场景 18 的「下一段戏」） ----
export interface LiveScriptStep {
  afterMs: number // 距上一条的间隔
  type: Message['type']
  characterId: string | null
  content: string
  innerThought: string | null
  chapter: string | null
  importance?: number
  milestone?: { chapter: string; summary: string } // 在这条消息之后触发里程碑
}

export const LIVE_SCRIPTS: Record<string, LiveScriptStep[]> = {
  'scene-18': [
    { afterMs: 6000, type: 'env', characterId: null, content: '雨又下起来了，先是几滴，然后密成一片。', innerThought: null, chapter: '雨幕', importance: 4 },
    { afterMs: 9000, type: 'dialogue', characterId: SHEN, content: '「新项目的事，顾遥找过你了？」', innerThought: '换个话题吧，总不能一直沉默。', chapter: '雨幕' },
    {
      afterMs: 9000,
      type: 'dialogue',
      characterId: LIN,
      content: '「找了。他想做可视化那块。」',
      innerThought: '他主动挑起话题了，难得。',
      chapter: '雨幕',
      importance: 4,
    },
    { afterMs: 10000, type: 'dialogue', characterId: SHEN, content: '「他适合。就是别让他又一个人扛。」', innerThought: '上次顾遥连续通宵了一周。', chapter: '雨幕', importance: 6, milestone: { chapter: '雨幕', summary: 'deadline 冲突缓和，两人并肩面对新的雨幕' } },
    { afterMs: 8000, type: 'env', characterId: null, content: '雨点打在窗台上，溅起细小的水花。', innerThought: null, chapter: '雨幕' },
    { afterMs: 9000, type: 'dialogue', characterId: LIN, content: '「这次不会了。我盯着。」', innerThought: '他在担心顾遥。这个人，嘴上不说。', chapter: '雨幕', importance: 5 },
    { afterMs: 10000, type: 'dialogue', characterId: SHEN, content: '「……你盯着就好。」', innerThought: '有她这句话，够了。', chapter: '雨幕', importance: 5 },
    { afterMs: 8000, type: 'env', characterId: null, content: '茶水间的灯又亮了一盏，雨声里，两个人的影子落在同一片瓷砖上。', innerThought: null, chapter: '雨幕', importance: 4 },
  ],
}
