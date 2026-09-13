import { useEffect, useMemo, useState } from 'react'
import {
  BookOpen,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Clock3,
  Command,
  FilePlus2,
  FolderOpen,
  History,
  Menu,
  MoreHorizontal,
  PanelRight,
  Play,
  Plus,
  Save,
  Search,
  Send,
  Settings2,
  Sparkles,
  Undo2,
  WandSparkles,
  X,
} from 'lucide-react'

type Chapter = {
  id: string
  title: string
  position: number
  status: string
  content?: string
  content_hash?: string
  word_count?: number
}

type Volume = { id: string; title: string; position: number; chapters: Chapter[] }
type Project = { id: string; name: string; description?: string | null; language: string }
type TreeResponse = { project: Project; volumes: Volume[] }

const demoTree: TreeResponse = {
  project: { id: 'demo-project', name: '潮汐之上', description: '一部关于记忆、航海与重逢的长篇小说。', language: 'zh-CN' },
  volumes: [
    {
      id: 'demo-volume-1',
      title: '第一卷 远岸灯火',
      position: 0,
      chapters: [
        { id: 'demo-chapter-1', title: '一、雾中的信', position: 0, status: 'draft', word_count: 1280 },
        { id: 'demo-chapter-2', title: '二、潮汐表', position: 1, status: 'draft', word_count: 2048 },
        { id: 'demo-chapter-3', title: '三、失真的星图', position: 2, status: 'outline', word_count: 0 },
      ],
    },
    {
      id: 'demo-volume-2',
      title: '第二卷 深海回声',
      position: 1,
      chapters: [{ id: 'demo-chapter-4', title: '四、回声井', position: 0, status: 'outline', word_count: 0 }],
    },
  ],
}

const demoContent = `凌晨四点十七分，灯塔还没有熄灭。

林默把信纸贴在舷窗上。雾气将远处的海面揉成一片灰白，只有那盏灯，每隔七秒从雾里探出一次，像有人在岸边眨眼。

信上没有署名，只有一行被海水晕开的字：

“当潮汐倒流，去找第七码头。”

他已经十年没有回过这座港口。十年前的那场风暴带走了父亲，也带走了他关于那一夜的大部分记忆。` 

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) throw new Error(`API ${response.status}`)
  return response.json() as Promise<T>
}

function App() {
  const [tree, setTree] = useState<TreeResponse>(demoTree)
  const [selectedId, setSelectedId] = useState('demo-chapter-1')
  const [content, setContent] = useState(demoContent)
  const [savedContent, setSavedContent] = useState(demoContent)
  const [isLoading, setIsLoading] = useState(true)
  const [saveState, setSaveState] = useState<'saved' | 'dirty' | 'saving' | 'offline'>('saved')
  const [assistantTab, setAssistantTab] = useState<'assistant' | 'history'>('assistant')
  const [assistantInput, setAssistantInput] = useState('')
  const [assistantLog, setAssistantLog] = useState<string[]>(['我可以帮你续写、改写选区，或检查本章的节奏与人物状态。'])
  const [openVolumes, setOpenVolumes] = useState<Record<string, boolean>>({ 'demo-volume-1': true, 'demo-volume-2': false })
  const [notice, setNotice] = useState('')

  const selectedChapter = useMemo(
    () => tree.volumes.flatMap((volume) => volume.chapters).find((chapter) => chapter.id === selectedId),
    [tree, selectedId],
  )
  const wordCount = content.replace(/\s/g, '').length

  useEffect(() => {
    const load = async () => {
      try {
        const projects = await api<Project[] | { items: Project[] }>('/api/v1/projects?page=1&page_size=1')
        const first = Array.isArray(projects) ? projects[0] : projects.items[0]
        if (!first) throw new Error('empty')
        const loadedTree = await api<TreeResponse>(`/api/v1/projects/${first.id}/tree`)
        setTree(loadedTree)
        const firstChapter = loadedTree.volumes[0]?.chapters[0]
        if (firstChapter) {
          setSelectedId(firstChapter.id)
          const loaded = await api<Chapter>(`/api/v1/chapters/${firstChapter.id}`)
          setContent(loaded.content ?? '')
          setSavedContent(loaded.content ?? '')
        }
      } catch {
        setSaveState('offline')
      } finally {
        setIsLoading(false)
      }
    }
    void load()
  }, [])

  useEffect(() => {
    if (!selectedId) return
    const draft = localStorage.getItem(`novel-workbench:draft:${selectedId}`)
    if (draft && draft !== savedContent) {
      setContent(draft)
      setSaveState('dirty')
    }
  }, [selectedId, savedContent])

  useEffect(() => {
    if (content === savedContent) return
    setSaveState('dirty')
    const timer = window.setTimeout(() => {
      localStorage.setItem(`novel-workbench:draft:${selectedId}`, content)
    }, 400)
    return () => window.clearTimeout(timer)
  }, [content, savedContent, selectedId])

  const selectChapter = async (chapter: Chapter) => {
    setSelectedId(chapter.id)
    setNotice('')
    const cached = localStorage.getItem(`novel-workbench:draft:${chapter.id}`)
    if (cached) {
      setContent(cached)
      setSavedContent(cached)
      return
    }
    try {
      const loaded = await api<Chapter>(`/api/v1/chapters/${chapter.id}`)
      setContent(loaded.content ?? '')
      setSavedContent(loaded.content ?? '')
      setSaveState('saved')
    } catch {
      setContent(chapter.id === 'demo-chapter-1' ? demoContent : '')
      setSavedContent(chapter.id === 'demo-chapter-1' ? demoContent : '')
      setSaveState('offline')
    }
  }

  const saveChapter = async () => {
    if (!selectedChapter || content === savedContent) return
    setSaveState('saving')
    try {
      const operation = await api<{ id: string }>('/api/v1/operations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: tree.project.id,
          target_id: selectedChapter.id,
          type: 'replace_range',
          payload: { from: 0, to: savedContent.length, new_text: content },
          old_hash: undefined,
          idempotency_key: `editor-${selectedChapter.id}-${Date.now()}`,
        }),
      })
      await api(`/api/v1/operations/${operation.id}/approve`, { method: 'POST' })
      setSavedContent(content)
      localStorage.removeItem(`novel-workbench:draft:${selectedChapter.id}`)
      setSaveState('saved')
      setNotice('已保存为新版本')
    } catch {
      localStorage.setItem(`novel-workbench:draft:${selectedChapter.id}`, content)
      setSaveState('offline')
      setNotice('已保存到本地草稿，连接后可提交')
    }
  }

  const sendAssistant = () => {
    const prompt = assistantInput.trim()
    if (!prompt) return
    setAssistantLog((items) => [...items, `你：${prompt}`, '建议：先明确这一段的冲突目标，再让林默在动作中暴露记忆缺口。'])
    setAssistantInput('')
  }

  return (
    <div className="app-shell">
      <header className="topbar">
          <div className="brand-lockup"><div className="brand-mark"><BookOpen size={16} /></div><span>novel / workbench</span></div>
          <div className="crumbs"><span>{tree.project.name}</span><span className="crumb-slash">/</span><span className="active-crumb">{selectedChapter?.title ?? '选择章节'}</span></div>
        <div className="top-actions">
          <div className={`save-indicator ${saveState}`}><span className="status-dot" />{saveState === 'saved' ? '已保存' : saveState === 'saving' ? '保存中' : saveState === 'offline' ? '本地草稿' : '未保存'}</div>
          <button className="icon-button" title="搜索"><Search size={17} /></button>
          <button className="icon-button" title="设置"><Settings2 size={17} /></button>
          <div className="avatar">LM</div>
        </div>
      </header>

      <div className="workspace">
        <aside className="sidebar left-sidebar">
          <div className="sidebar-heading"><span>作品结构</span><button className="icon-button subtle" title="新建"><Plus size={16} /></button></div>
          <div className="project-summary"><div className="project-cover">潮<br />汐</div><div><strong>{tree.project.name}</strong><span>{tree.project.description ?? '本地创作项目'}</span></div></div>
          <div className="tree-actions"><button><FilePlus2 size={14} />新章节</button><button><FolderOpen size={14} />打开项目</button></div>
          <div className="tree-list">
            {tree.volumes.map((volume) => {
              const open = openVolumes[volume.id] ?? true
              return <div className="volume" key={volume.id}>
                <button className="volume-row" onClick={() => setOpenVolumes((state) => ({ ...state, [volume.id]: !open }))}>{open ? <ChevronDown size={15} /> : <ChevronRight size={15} />}<span>{volume.title}</span><MoreHorizontal size={15} className="row-more" /></button>
                {open && <div className="chapter-list">{volume.chapters.map((chapter) => <button key={chapter.id} className={`chapter-row ${chapter.id === selectedId ? 'selected' : ''}`} onClick={() => void selectChapter(chapter)}><span className="chapter-index">{String(chapter.position + 1).padStart(2, '0')}</span><span className="chapter-title">{chapter.title.replace(/^\S+、/, '')}</span>{chapter.status === 'outline' ? <span className="outline-tag">提纲</span> : <span className="chapter-count">{chapter.word_count ? `${chapter.word_count}` : '—'}</span>}</button>)}</div>}
              </div>
            })}
          </div>
          <button className="sidebar-footer"><CircleHelp size={16} />工作区指南 <span>⌘ /</span></button>
        </aside>

        <main className="editor-pane">
          <div className="editor-toolbar">
            <div className="toolbar-group"><button className="tool-button" title="撤销"><Undo2 size={16} /></button><button className="tool-button disabled" title="重做"><Undo2 size={16} style={{ transform: 'scaleX(-1)' }} /></button><span className="toolbar-divider" /><button className="tool-button active" title="写作模式"><WandSparkles size={16} />写作</button><button className="tool-button" title="大纲模式"><Command size={16} />大纲</button></div>
            <div className="toolbar-group"><span className="editor-stat">{wordCount.toLocaleString()} 字</span><button className="tool-button" title="历史版本" onClick={() => setAssistantTab('history')}><History size={16} /></button><button className="tool-button save-button" onClick={() => void saveChapter()} title="保存"><Save size={16} />保存版本</button></div>
          </div>
          <div className="editor-scroll">
            <article className="chapter-header"><div className="eyebrow">第一卷 · 远岸灯火</div><h1>{selectedChapter?.title ?? '未命名章节'}</h1><p>草稿 · 最后编辑于今天 04:17</p></article>
            {isLoading ? <div className="loading-state">正在打开作品…</div> : <textarea className="writing-surface" value={content} onChange={(event) => setContent(event.target.value)} spellCheck={false} aria-label="章节正文" />}
            <div className="editor-bottom"><span><span className="bottom-dot" />自动保存已开启</span><span>Markdown · UTF-8</span></div>
          </div>
        </main>

        <aside className="sidebar right-sidebar">
          <div className="assistant-head"><div className="tab-switch"><button className={assistantTab === 'assistant' ? 'active' : ''} onClick={() => setAssistantTab('assistant')}><Sparkles size={15} />助手</button><button className={assistantTab === 'history' ? 'active' : ''} onClick={() => setAssistantTab('history')}><Clock3 size={15} />版本</button></div><button className="icon-button subtle" title="收起侧栏"><PanelRight size={17} /></button></div>
          {assistantTab === 'assistant' ? <>
            <div className="assistant-context"><div className="context-label">当前上下文</div><div className="context-row"><span className="context-icon"><BookOpen size={14} /></span><span>第 1 章 · 全文</span><span className="context-meta">{wordCount} 字</span></div><div className="context-row"><span className="context-icon violet"><Sparkles size={14} /></span><span>潮汐之上 · 写作规则</span><span className="context-meta">已加载</span></div></div>
            <div className="assistant-log">{assistantLog.map((line, index) => <div key={`${line}-${index}`} className={line.startsWith('你：') ? 'user-line' : line.startsWith('建议：') ? 'suggestion-line' : 'assistant-line'}>{line.startsWith('建议：') && <Sparkles size={14} />}{line}</div>)}</div>
            <div className="quick-prompts"><span>快速操作</span><div><button onClick={() => setAssistantInput('续写这一段，保持克制的悬疑感')}><Play size={13} />续写</button><button onClick={() => setAssistantInput('把这段改得更有画面感')}><WandSparkles size={13} />改写</button><button onClick={() => setAssistantInput('检查人物动机和时间线')}><Search size={13} />检查</button></div></div>
            <div className="assistant-compose"><textarea placeholder="告诉助手你想做什么…" value={assistantInput} onChange={(event) => setAssistantInput(event.target.value)} onKeyDown={(event) => { if (event.key === 'Enter' && (event.metaKey || event.ctrlKey)) sendAssistant() }} /><div className="compose-footer"><span>⌘ ↵ 发送</span><button className="send-button" onClick={sendAssistant} title="发送"><Send size={15} /></button></div></div>
          </> : <div className="history-panel"><div className="history-intro"><History size={17} /><div><strong>版本时间线</strong><p>每次审批都会生成一个可恢复版本。</p></div></div><div className="history-item current"><span className="history-dot" /><div><strong>当前草稿</strong><span>今天 04:17 · {wordCount} 字</span></div><MoreHorizontal size={15} /></div><div className="history-item"><span className="history-dot" /><div><strong>初始版本</strong><span>今天 03:52 · 1,280 字</span></div><MoreHorizontal size={15} /></div><button className="history-close" onClick={() => setAssistantTab('assistant')}><X size={14} />返回助手</button></div>}
        </aside>
      </div>
      {notice && <button className="toast" onClick={() => setNotice('')}>{notice}<X size={14} /></button>}
      <button className="mobile-menu" title="菜单"><Menu size={18} /></button>
    </div>
  )
}

export default App
